#!/usr/bin/env python3
"""
Comic frame generator for Soviet comic-noir story.

Pipeline:
  1. Load story.txt + characters.json
  2. LLM (Gemini Flash, fallback Pro) splits story into scene blocks
  3. For each scene: LLM builds a detailed English prompt + resolves which
     characters from characters.json appear (auto-picks correct age variant
     based on scene context).
  4. If a character is mentioned but has no entry in characters.json:
       - LLM generates a description and writes it to characters.json.
       - The scene is SKIPPED (error logged) because there is no ref image.
  5. Nano-banana (gemini-2.5-flash-image) generates the image with all
     referenced character images attached.
  6. Output: output/frame_XXX.png + prompts.json + progress.json (resume).

Usage:
  export GEMINI_API_KEY=...
  python generate_comic.py --story story.txt --characters characters.json
  python generate_comic.py --story story.txt --dry-run        # prompts only
  python generate_comic.py --story story.txt --resume         # continue
  python generate_comic.py --story story.txt --force-pro      # Pro for all
"""

import argparse
import base64
import json
import logging
import os
import random
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any
from pydantic import BaseModel, ValidationError

from schemas import (
    CharactersResponse,
    DesignSpec,
    ScenePromptResponse,
    SplitResponse,
)

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:
    print("ERROR: install google-genai:  pip install google-genai", file=sys.stderr)
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# ──────────────────────────────────────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────────────────────────────────────

STYLE_SUFFIX = (
    "16:9 ratio. Style: Soviet comic-noir, thick heavy ink outlines, "
    "cinematic cel-shaded illustration, gritty atmosphere, teal and amber "
    "color palette, high contrast, dramatic lighting, detailed cross-hatching, "
    "moody urban aesthetic. "
    "Composition: keep the bottom 20% visually calmer and darker — a subtitle "
    "safe zone; no critical faces or action in the lower fifth. "
    "Do NOT render any text, letters, words, captions, signs, speech bubbles "
    "or comic balloons inside the image."
)

# Reference-portrait style (used by bootstrap to pre-generate refs).
PORTRAIT_STYLE_SUFFIX = (
    "Character reference sheet: full body or 3/4 portrait, neutral expression, "
    "front-facing, isolated on a plain dark background, even lighting so the "
    "character's features are clearly legible. Same Soviet comic-noir style: "
    "thick ink outlines, cel-shaded, teal and amber palette. "
    "No text, no letters, no captions, no watermark."
)

# Subtitle / timing constants
SUBTITLE_MAX_CHARS_PER_LINE = 42
SUBTITLE_MAX_LINES = 2
RU_WORDS_PER_SEC = 2.5       # Russian TTS typical pace
MIN_SCENE_DURATION = 3.0     # seconds
MAX_SCENE_DURATION = 12.0    # seconds, cap for pacing

FLASH_MODEL = "gemini-2.5-flash"
PRO_MODEL = "gemini-2.5-pro"
FLASH_FALLBACK_MODEL = "gemini-2.5-flash-lite"
PRO_FALLBACK_MODEL = "gemini-2.5-flash"
IMAGE_MODEL = "gemini-2.5-flash-image"  # "nano-banana" (preview model)

# Heuristics for auto-escalation Flash -> Pro
COMPLEX_SCENE_CHAR_THRESHOLD = 4        # more than N chars in a scene
COMPLEX_SCENE_LENGTH_CHARS = 900        # long scene text
MAX_RETRIES = 8                         # text LLM retries
IMAGE_MAX_RETRIES = 10                  # image model retries (preview, flaky)
BACKOFF_BASE = 2.0                      # exponential backoff base (seconds)
BACKOFF_CAP = 120.0                     # max single backoff (seconds)
BACKOFF_CAP_503 = 300.0                 # longer cap for server overload
FAST_FALLBACK_OVERLOAD_THRESHOLD = 3    # jump to fallback after N consec 503s

log = logging.getLogger("comic")


# ──────────────────────────────────────────────────────────────────────────────
# DATA MODELS
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class Scene:
    index: int
    text: str                           # original Russian excerpt
    title: str = ""                     # short label from LLM
    character_ids: list[str] = field(default_factory=list)
    prompt: str = ""                    # final English prompt for image model
    status: str = "pending"             # pending | ok | skipped | error
    error: str = ""
    image_path: str = ""
    model_used: str = ""
    # Voice / subtitles metadata (filled by scene LLM pass)
    voice_text: str = ""                # clean RU text for TTS
    speaker: str = "narrator"           # "narrator" | <character_id>
    emotion: str = ""                   # e.g. "melancholic", "tense"
    pacing: str = "normal"              # "slow" | "normal" | "fast"
    duration_sec: float = 0.0           # estimated clip length
    subtitle_lines: list[str] = field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────────────
# LLM helpers
# ──────────────────────────────────────────────────────────────────────────────

# Error kinds worth distinguishing for backoff policy.
# Everything not classified here is treated as RETRY_SHORT.
RETRYABLE_STATUSES = {
    "429": "rate_limit",       # quota — wait longer, honor Retry-After
    "500": "server",           # transient server
    "502": "server",
    "503": "overload",         # model overloaded — wait much longer
    "504": "timeout",
    "UNAVAILABLE": "overload",
    "RESOURCE_EXHAUSTED": "rate_limit",
    "DEADLINE_EXCEEDED": "timeout",
    "INTERNAL": "server",
}

FATAL_STATUSES = {"400", "401", "403", "404",
                  "INVALID_ARGUMENT", "PERMISSION_DENIED", "NOT_FOUND"}


def classify_error(err: Exception) -> tuple[str, float | None]:
    """Return (kind, retry_after_seconds). kind ∈
    {"rate_limit","overload","server","timeout","fatal","unknown"}."""
    msg = str(err)
    for status in FATAL_STATUSES:
        if status in msg:
            return "fatal", None
    # look for Retry-After / retryDelay: "42s" in the error payload
    retry_after = None
    m = re.search(r"retry[_-]?(?:after|delay)\"?\s*[:=]\s*\"?(\d+)",
                  msg, flags=re.IGNORECASE)
    if m:
        retry_after = float(m.group(1))
    else:
        m = re.search(r"(\d+)s['\"]?\s*}", msg)  # "...42s"}
        if m:
            retry_after = float(m.group(1))
    for status, kind in RETRYABLE_STATUSES.items():
        if status in msg:
            return kind, retry_after
    return "unknown", retry_after


def backoff_delay(attempt: int, kind: str,
                  retry_after: float | None = None) -> float:
    """Full-jitter exponential backoff. attempt starts at 0."""
    if retry_after is not None:
        # Respect server's hint + small jitter.
        return retry_after + random.uniform(0.5, 3.0)
    cap = BACKOFF_CAP_503 if kind in ("overload", "rate_limit") else BACKOFF_CAP
    # For overload / rate_limit, start higher so we actually let the fire cool.
    base = BACKOFF_BASE * (4.0 if kind in ("overload", "rate_limit") else 1.0)
    exp = min(cap, base * (2 ** attempt))
    return random.uniform(base, exp)


def call_llm_json(client: genai.Client, model: str, prompt: str,
                  system: str | None = None,
                  deterministic: bool = False,
                  schema: type[BaseModel] | None = None) -> Any:
    """Call LLM and parse JSON from the response.

    Robust to 429/503/5xx with full-jitter exponential backoff and
    Retry-After honoring. Falls back to a cheaper model after exhausting
    retries.

    If schema is provided, validates the parsed JSON against it. On
    ValidationError, re-prompts the LLM with the error detail attached,
    consuming the retry budget. Returns result.model_dump() so callers
    using data.get(...) keep working unchanged.

    deterministic=True forces temperature=0 and disables thinking.
    """
    cfg_kwargs: dict[str, Any] = {
        "response_mime_type": "application/json",
        "system_instruction": system,
    }
    if deterministic:
        cfg_kwargs["temperature"] = 0.0
        cfg_kwargs["thinking_config"] = genai_types.ThinkingConfig(
            thinking_budget=0,
        )
    cfg = genai_types.GenerateContentConfig(**cfg_kwargs)
    fallback = FLASH_FALLBACK_MODEL if model == FLASH_MODEL else (
        PRO_FALLBACK_MODEL if model == PRO_MODEL else None
    )
    base_prompt = prompt
    current_prompt = base_prompt
    last_err: Exception | None = None
    consec_overload = 0
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = client.models.generate_content(
                model=model, contents=current_prompt, config=cfg,
            )
            text = (resp.text or "").strip()
            # strip ```json fences just in case
            text = re.sub(r"^```(?:json)?|```$", "", text,
                          flags=re.MULTILINE).strip()
            data = json.loads(text)

            if schema is not None:
                try:
                    return schema.model_validate(data).model_dump()
                except ValidationError as ve:
                    last_err = ve
                    log.warning(
                        "Schema validation failed on %s (attempt %d/%d): %s",
                        model, attempt + 1, MAX_RETRIES + 1, ve,
                    )
                    current_prompt = (
                        base_prompt
                        + "\n\nPREVIOUS RESPONSE FAILED SCHEMA VALIDATION:\n"
                        + str(ve)
                        + "\n\nReturn valid JSON matching the schema exactly."
                    )
                    kind, retry_after = "validation", None
                    consec_overload = 0
                    # fall through to backoff
                else:
                    # pragma: no cover - unreachable, success path returned above
                    pass
            else:
                return data
        except json.JSONDecodeError as e:
            last_err = e
            kind, retry_after = "unknown", None
            consec_overload = 0
            log.warning("LLM returned invalid JSON on %s (attempt %d/%d): %s",
                        model, attempt + 1, MAX_RETRIES + 1, e)
        except Exception as e:
            last_err = e
            kind, retry_after = classify_error(e)
            if kind == "fatal":
                log.error("Fatal API error on %s: %s", model, e)
                raise
            consec_overload = consec_overload + 1 if kind == "overload" else 0
            log.warning("LLM call failed on %s (attempt %d/%d) [%s]: %s",
                        model, attempt + 1, MAX_RETRIES + 1, kind, e)

        # Fast fallback: if model is persistently overloaded, jump early
        # to the fallback model instead of burning more retry budget.
        if consec_overload >= FAST_FALLBACK_OVERLOAD_THRESHOLD and fallback:
            log.warning("%s overloaded x%d, switching to fallback %s early",
                        model, consec_overload, fallback)
            return call_llm_json(client, fallback, base_prompt, system=system,
                                 deterministic=deterministic, schema=schema)

        if attempt >= MAX_RETRIES:
            break
        wait = backoff_delay(attempt, kind, retry_after)
        log.info("Waiting %.1fs before retry...", wait)
        time.sleep(wait)

    if fallback:
        log.warning("All retries exhausted for %s, trying fallback %s",
                    model, fallback)
        return call_llm_json(client, fallback, base_prompt, system=system,
                             deterministic=deterministic, schema=schema)
    raise RuntimeError(f"LLM failed after retries: {last_err}")


def pick_scene_model(scene_text: str, expected_chars: int,
                     force_pro: bool = False) -> str:
    """Auto-escalate to Pro for complex scenes."""
    if force_pro:
        return PRO_MODEL
    if expected_chars >= COMPLEX_SCENE_CHAR_THRESHOLD:
        return PRO_MODEL
    if len(scene_text) >= COMPLEX_SCENE_LENGTH_CHARS:
        return PRO_MODEL
    return FLASH_MODEL


# ──────────────────────────────────────────────────────────────────────────────
# STEP 1: split story into scenes
# ──────────────────────────────────────────────────────────────────────────────

SPLIT_SYSTEM = """You split Russian literary prose into cinematic scene blocks
for a graphic novel. Each scene = one visual moment / one frame.
Rules:
- Split by semantic unit (action beat, emotional beat, location change,
  time jump), NOT by sentence.
- A scene can be 1–6 sentences of source text.
- Keep the ORIGINAL Russian text verbatim in the 'text' field.
- Give each scene a short English 'title' (3–6 words).
- Do not add commentary. Output valid JSON only."""

SPLIT_PROMPT = """Split the following Russian story into scene blocks for a
graphic novel.

Return JSON of this exact shape:
{{"scenes": [{{"title": "short english label", "text": "verbatim russian excerpt"}}]}}

STORY:
<<<
{story}
>>>"""


def split_story(client: genai.Client, story: str, model: str) -> list[Scene]:
    log.info("Splitting story with %s (deterministic) ...", model)
    data = call_llm_json(client, model,
                         SPLIT_PROMPT.format(story=story),
                         system=SPLIT_SYSTEM,
                         deterministic=True)
    scenes = []
    for i, s in enumerate(data.get("scenes", []), start=1):
        scenes.append(Scene(index=i,
                            text=s["text"].strip(),
                            title=s.get("title", "").strip()))
    log.info("Story split into %d scenes", len(scenes))
    return scenes


# ──────────────────────────────────────────────────────────────────────────────
# STEP 2: for each scene — resolve characters & build prompt
# ──────────────────────────────────────────────────────────────────────────────

SCENE_SYSTEM = """You design single frames of a Soviet comic-noir graphic
novel AND prepare voiceover / subtitle metadata for each frame. For each
scene you receive:
  - the Russian source excerpt
  - the full character dossier (id -> name + visual description)

Your job:
1. Identify which characters from the dossier APPEAR IN THIS SPECIFIC FRAME.
   Pick EXACT ids from the dossier. For the protagonist Алексей/Лёша,
   choose the correct age variant (lyosha_5, lyosha_8, lyosha_12, lyosha_15,
   aleksey_17, aleksey_18, aleksey_19, aleksey_38) by reading the YEAR
   mentioned in the scene and the protagonist's stated age. Use the wider
   story context to infer.
2. Detect any NEW named character who is NOT in the dossier. For each new
   one provide a full visual description (age, build, hair, clothing, props,
   distinguishing marks) in the same style as existing entries.
3. Write a single-paragraph cinematic English prompt for an image model,
   describing: environment, composition, lighting, what each character is
   DOING, wearing, feeling. Reference named characters by their dossier id
   in curly braces, e.g. {aleksey_38}. Do NOT re-describe characters that
   are in the dossier — the image model receives their reference images.
   DO describe new characters inline since they have no reference yet.
   The prompt MUST reflect the scene's emotion on the characters' faces.
4. Do not add style tokens (palette, line weight, ratio) — those are appended
   automatically.
5. Produce voice / subtitle metadata:
   - voice_text: the Russian text to be read aloud for this frame. Usually
     == the source excerpt, but cleaned from stage directions or visual
     notes in parentheses. Keep it natural spoken Russian.
   - speaker: "narrator" by default, OR the dossier id of the character
     whose direct speech is quoted in the excerpt.
   - emotion: 1-3 words, lowercase english, e.g. "melancholic",
     "tense alert", "warm nostalgic".
   - pacing: "slow" | "normal" | "fast" — how fast the narrator should read.
   - subtitle_lines: 1-3 short Russian lines, each ≤ 42 characters,
     splitting voice_text at natural pauses for on-screen subtitles.

Output JSON exactly:
{
  "existing_character_ids": ["id1", "id2"],
  "new_characters": [
    {"id": "snake_case_id", "name": "Имя на русском", "description": "full english visual description"}
  ],
  "prompt": "cinematic english paragraph describing the frame",
  "voice_text": "русский текст для озвучки",
  "speaker": "narrator",
  "emotion": "melancholic",
  "pacing": "normal",
  "subtitle_lines": ["строка 1", "строка 2"]
}"""

SCENE_PROMPT = """CHARACTER DOSSIER:
{dossier}

STORY CONTEXT (full story, for age/timeline inference):
<<<
{story}
>>>

CURRENT SCENE (frame to draw):
<<<
{scene}
>>>

Return the JSON described in the system instruction."""


def build_scene_prompt(client: genai.Client, scene: Scene,
                       characters: dict, story: str,
                       force_pro: bool = False) -> tuple[dict, str]:
    dossier = json.dumps(
        {cid: {"name": c["name"], "description": c["description"]}
         for cid, c in characters.items()},
        ensure_ascii=False, indent=2,
    )
    # we don't know char count yet — use Flash first, escalate on failure
    model = pick_scene_model(scene.text, expected_chars=0,
                             force_pro=force_pro)
    prompt = SCENE_PROMPT.format(dossier=dossier, story=story,
                                 scene=scene.text)
    try:
        data = call_llm_json(client, model, prompt, system=SCENE_SYSTEM)
    except Exception as e:
        if model == FLASH_MODEL and not force_pro:
            log.warning("Flash failed for scene %d, escalating to Pro: %s",
                        scene.index, e)
            data = call_llm_json(client, PRO_MODEL, prompt,
                                 system=SCENE_SYSTEM)
            model = PRO_MODEL
        else:
            raise
    # auto-escalate to Pro if many characters involved
    n_chars = len(data.get("existing_character_ids", [])) + \
              len(data.get("new_characters", []))
    if n_chars >= COMPLEX_SCENE_CHAR_THRESHOLD and model == FLASH_MODEL \
            and not force_pro:
        log.info("Scene %d has %d chars, re-running on Pro",
                 scene.index, n_chars)
        data = call_llm_json(client, PRO_MODEL, prompt, system=SCENE_SYSTEM)
        model = PRO_MODEL
    return data, model


# ──────────────────────────────────────────────────────────────────────────────
# STEP 2b: BATCH prompt building (50% cheaper, avoids realtime 503 storms)
# Batch API does NOT support image models — only text LLM calls.
# ──────────────────────────────────────────────────────────────────────────────

BATCH_POLL_INTERVAL = 60.0
BATCH_POLL_TIMEOUT = 60 * 60 * 6        # 6h (docs say up to 24h)
BATCH_COMPLETED_STATES = {
    "JOB_STATE_SUCCEEDED",
    "JOB_STATE_FAILED",
    "JOB_STATE_CANCELLED",
    "JOB_STATE_EXPIRED",
}


def _batch_scene_request(scene: Scene, characters: dict,
                         story: str) -> dict:
    dossier = json.dumps(
        {cid: {"name": c["name"], "description": c["description"]}
         for cid, c in characters.items()},
        ensure_ascii=False, indent=2,
    )
    user_text = SCENE_PROMPT.format(dossier=dossier, story=story,
                                    scene=scene.text)
    return {
        "contents": [{"parts": [{"text": user_text}], "role": "user"}],
        "config": {
            "system_instruction": {"parts": [{"text": SCENE_SYSTEM}]},
            "response_mime_type": "application/json",
        },
    }


def _parse_batch_response_text(text: str) -> dict:
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?|```$", "", text,
                  flags=re.MULTILINE).strip()
    return json.loads(text)


def batch_create_scene_prompts(
    client: genai.Client, scenes: list[Scene], characters: dict,
    story: str, model: str,
) -> tuple[str, list[Scene]]:
    """Submit a batch job for all pending scene-prompt requests.
    Returns (job_name, pending_scenes_in_order)."""
    pending = [s for s in scenes if s.status not in ("ok", "skipped")
               and not s.prompt]
    if not pending:
        return "", []

    inline = [_batch_scene_request(s, characters, story) for s in pending]
    log.info("Submitting batch: %d scene prompts on %s ...",
             len(pending), model)
    job = client.batches.create(
        model=model, src=inline,
        config={"display_name": f"comic-scenes-{int(time.time())}"},
    )
    log.info("Batch job created: %s", job.name)
    return job.name, pending


def batch_collect_scene_prompts(
    client: genai.Client, job_name: str, pending: list[Scene], model: str,
) -> dict[int, tuple[dict | None, str, str | None]]:
    """Poll a batch job to completion and parse inline responses.
    Returns {scene.index: (data_or_none, model_used, error_or_none)}."""
    start = time.time()
    while True:
        job = client.batches.get(name=job_name)
        state = job.state.name
        if state in BATCH_COMPLETED_STATES:
            break
        if time.time() - start > BATCH_POLL_TIMEOUT:
            raise RuntimeError(f"Batch timed out after {BATCH_POLL_TIMEOUT}s "
                               f"(last state={state})")
        log.info("Batch state: %s (%.0fs elapsed)",
                 state, time.time() - start)
        time.sleep(BATCH_POLL_INTERVAL)

    if job.state.name != "JOB_STATE_SUCCEEDED":
        raise RuntimeError(f"Batch job ended in {job.state.name}: "
                           f"{getattr(job, 'error', None)}")

    results: dict[int, tuple[dict | None, str, str | None]] = {}
    responses = list(job.dest.inlined_responses)
    if len(responses) != len(pending):
        log.warning("Batch returned %d responses, expected %d",
                    len(responses), len(pending))

    for scene, resp in zip(pending, responses):
        if getattr(resp, "error", None):
            results[scene.index] = (None, model, str(resp.error))
            continue
        try:
            data = _parse_batch_response_text(resp.response.text)
            results[scene.index] = (data, model, None)
        except Exception as e:
            results[scene.index] = (None, model, f"parse failed: {e}")
    return results


# ──────────────────────────────────────────────────────────────────────────────
# STEP 3: image generation via nano-banana
# ──────────────────────────────────────────────────────────────────────────────

def generate_image(client: genai.Client, prompt: str,
                   ref_image_paths: list[Path],
                   out_path: Path) -> bool:
    parts: list[Any] = []
    for p in ref_image_paths:
        if not p.exists():
            log.warning("Missing reference: %s", p)
            continue
        data = p.read_bytes()
        mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
        parts.append(genai_types.Part.from_bytes(data=data, mime_type=mime))
    parts.append(prompt)

    last_err: Any = None
    for attempt in range(IMAGE_MAX_RETRIES + 1):
        try:
            resp = client.models.generate_content(
                model=IMAGE_MODEL, contents=parts,
            )
            for part in resp.candidates[0].content.parts:
                if getattr(part, "inline_data", None) and \
                        part.inline_data.data:
                    blob = part.inline_data.data
                    if isinstance(blob, str):  # base64
                        blob = base64.b64decode(blob)
                    out_path.write_bytes(blob)
                    return True
            last_err = "no image in response"
            kind, retry_after = "server", None
        except Exception as e:
            last_err = e
            kind, retry_after = classify_error(e)
            if kind == "fatal":
                log.error("Fatal image API error: %s", e)
                return False
            log.warning("Image gen failed (attempt %d/%d) [%s]: %s",
                        attempt + 1, IMAGE_MAX_RETRIES + 1, kind, e)

        if attempt >= IMAGE_MAX_RETRIES:
            break
        wait = backoff_delay(attempt, kind, retry_after)
        log.info("Waiting %.1fs before image retry...", wait)
        time.sleep(wait)
    log.error("Image gen gave up: %s", last_err)
    return False


# ──────────────────────────────────────────────────────────────────────────────
# STEP 4: BOOTSTRAP — extract characters from story + synth reference portraits
# ──────────────────────────────────────────────────────────────────────────────

BOOTSTRAP_SYSTEM = """You read a Russian literary text and build a COMPLETE
character dossier for a graphic-novel pipeline. For EACH named character
(protagonist, supporting, recurring minor roles):

- Pick a stable snake_case english id (e.g. "aleksey_38", "tanya",
  "dyadya_misha").
- Give the Russian name.
- Give a full english visual description: approximate age, build, face,
  hair, eyes, clothing typical for their appearance era, any distinctive
  props or marks. Written so an image model can draw a consistent portrait.
- If a character appears at multiple AGES in the story (e.g. the
  protagonist at 5, 12, 19, 38), emit one entry per age variant with
  distinct ids. Infer age from years / context in the text.

Output JSON exactly:
{
  "characters": [
    {"id": "...", "name": "...", "description": "...", "age": 38}
  ]
}
"age" is integer years if relevant, else null."""

BOOTSTRAP_PROMPT = """FULL STORY (Russian):
<<<
{story}
>>>

Return the JSON described in the system instruction."""


def bootstrap_characters(
    client: genai.Client, story: str, characters_path: Path,
    model: str, force: bool = False,
) -> dict:
    """Extract every named character from the story and write
    characters.json. Preserves existing entries unless force=True."""
    existing: dict = {}
    if characters_path.exists() and not force:
        existing = json.loads(characters_path.read_text(encoding="utf-8"))

    log.info("Bootstrap: scanning story for characters (%s) ...", model)
    data = call_llm_json(client, model,
                         BOOTSTRAP_PROMPT.format(story=story),
                         system=BOOTSTRAP_SYSTEM,
                         deterministic=True)
    added = 0
    for c in data.get("characters", []):
        cid = c["id"]
        if cid in existing:
            continue
        existing[cid] = {
            "name": c["name"],
            "reference_image": f"references/{cid}.png",
            "description": c["description"],
            "_auto_generated": True,
        }
        added += 1

    characters_path.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log.info("Bootstrap: %d new characters added (%d total)",
             added, len(existing))
    return existing


def generate_character_references(
    client: genai.Client, characters: dict, refs_dir: Path,
) -> int:
    """For every character whose reference_image is missing, call nano-banana
    to synthesize a portrait. Returns count of newly generated refs."""
    refs_dir.mkdir(parents=True, exist_ok=True)
    generated = 0
    missing = [(cid, c) for cid, c in characters.items()
               if not Path(c.get("reference_image",
                                  f"references/{cid}.png")).exists()]
    if not missing:
        log.info("All character references already exist")
        return 0
    log.info("Generating %d missing reference portraits ...", len(missing))
    for cid, c in missing:
        ref_path = Path(c.get("reference_image", f"references/{cid}.png"))
        ref_path.parent.mkdir(parents=True, exist_ok=True)
        portrait_prompt = (
            f"Portrait of {c['name']}. {c['description']}\n\n"
            f"{PORTRAIT_STYLE_SUFFIX}"
        )
        log.info("  → %s", ref_path)
        ok = generate_image(client, portrait_prompt, [], ref_path)
        if ok:
            generated += 1
        else:
            log.error("  failed to generate reference for %s", cid)
    log.info("Bootstrap: generated %d/%d references",
             generated, len(missing))
    return generated


# ──────────────────────────────────────────────────────────────────────────────
# STEP 5: DESIGN SPEC — LLM picks subtitle styling from story + visual style
# ──────────────────────────────────────────────────────────────────────────────

DESIGN_SPEC_SYSTEM = """You are a motion-graphics director. Given a Soviet
comic-noir visual style and the story's tone, propose on-screen subtitle
styling that reads well on the frames and matches the aesthetic.

Output JSON exactly:
{
  "font_family": "suggest a common web-safe font matching the mood",
  "font_weight": 600,
  "font_size_px": 42,
  "color_fg": "#HEX",
  "color_bg_gradient": ["#HEX_top", "#HEX_bottom"],
  "stroke_px": 2,
  "stroke_color": "#HEX",
  "position": "bottom_centered",
  "margin_bottom_pct": 8,
  "max_chars_per_line": 42,
  "max_lines": 2,
  "line_height": 1.3,
  "narrator_style": "italic",
  "dialogue_style": "regular",
  "rationale": "one-sentence explanation of how this fits the mood"
}"""

DESIGN_SPEC_PROMPT = """STORY EXCERPT (first 2000 chars, for tone):
<<<
{excerpt}
>>>

VISUAL STYLE:
<<<
{style}
>>>

Return the JSON described in the system instruction."""


def generate_design_spec(client: genai.Client, story: str,
                         model: str, out_path: Path) -> dict:
    log.info("Generating subtitle design spec (%s) ...", model)
    data = call_llm_json(client, model,
                         DESIGN_SPEC_PROMPT.format(
                             excerpt=story[:2000],
                             style=STYLE_SUFFIX),
                         system=DESIGN_SPEC_SYSTEM,
                         deterministic=True)
    out_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log.info("Design spec saved → %s", out_path)
    return data


# ──────────────────────────────────────────────────────────────────────────────
# STEP 6: SRT EXPORT — produce subtitles.srt from scenes
# ──────────────────────────────────────────────────────────────────────────────

def estimate_duration(voice_text: str, pacing: str = "normal") -> float:
    words = max(1, len(voice_text.split()))
    base = words / RU_WORDS_PER_SEC
    if pacing == "slow":
        base *= 1.3
    elif pacing == "fast":
        base *= 0.7
    return min(MAX_SCENE_DURATION, max(MIN_SCENE_DURATION, base))


def _fmt_srt_time(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def export_srt(scenes: list[Scene], out_path: Path) -> None:
    cursor = 0.0
    blocks: list[str] = []
    for i, scene in enumerate(scenes, start=1):
        if scene.status not in ("ok",):
            continue
        if not scene.voice_text and not scene.subtitle_lines:
            continue
        dur = scene.duration_sec or estimate_duration(
            scene.voice_text or scene.text, scene.pacing)
        start = cursor
        end = cursor + dur
        cursor = end
        lines = scene.subtitle_lines or [scene.voice_text or scene.text]
        blocks.append(
            f"{i}\n"
            f"{_fmt_srt_time(start)} --> {_fmt_srt_time(end)}\n"
            f"{chr(10).join(lines)}\n"
        )
    out_path.write_text("\n".join(blocks), encoding="utf-8")
    log.info("SRT exported → %s (%d cues, total %.1fs)",
             out_path, len(blocks), cursor)


# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--story", required=True, help="Path to story.txt")
    ap.add_argument("--characters", default="characters.json")
    ap.add_argument("--output-dir", default="output")
    ap.add_argument("--dry-run", action="store_true",
                    help="Build prompts, skip image generation")
    ap.add_argument("--resume", action="store_true",
                    help="Continue from progress.json")
    ap.add_argument("--force-pro", action="store_true",
                    help="Always use gemini-2.5-pro")
    ap.add_argument("--batch", action="store_true",
                    help="Use Batch API for scene-prompt building "
                         "(50%% cheaper, avoids 503 storms, async)")
    ap.add_argument("--bootstrap", action="store_true",
                    help="Before split: scan story for characters and "
                         "auto-generate missing reference portraits + "
                         "subtitle design spec. Enables full automation.")
    ap.add_argument("--bootstrap-force", action="store_true",
                    help="With --bootstrap, overwrite existing characters.json")
    ap.add_argument("--limit", type=int, default=0,
                    help="Process only first N scenes (0 = all)")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    api_key = os.environ.get("GEMINI_API_KEY") or \
              os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        sys.exit("ERROR: set GEMINI_API_KEY env var")

    client = genai.Client(api_key=api_key)

    story = Path(args.story).read_text(encoding="utf-8")
    chars_path = Path(args.characters)
    if chars_path.exists():
        characters = json.loads(chars_path.read_text(encoding="utf-8"))
    else:
        characters = {}
        chars_path.write_text("{}", encoding="utf-8")

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    progress_path = out_dir / "progress.json"
    prompts_path = out_dir / "prompts.json"
    design_spec_path = out_dir / "design_spec.json"
    srt_path = out_dir / "subtitles.srt"
    refs_dir = Path("references")

    # ── BOOTSTRAP: auto-build characters + reference portraits + design spec ─
    if args.bootstrap and not args.resume:
        bootstrap_model = PRO_MODEL if args.force_pro else FLASH_MODEL
        characters = bootstrap_characters(
            client, story, chars_path,
            model=bootstrap_model, force=args.bootstrap_force,
        )
        if not args.dry_run:
            generate_character_references(client, characters, refs_dir)
        else:
            log.info("[dry-run] skipping reference portrait generation")
        # Design spec always runs in bootstrap (tiny cost).
        if not design_spec_path.exists() or args.bootstrap_force:
            generate_design_spec(client, story, bootstrap_model,
                                 design_spec_path)

    # ── Load or create scenes ────────────────────────────────────────────
    scenes: list[Scene]
    saved_job_name: str | None = None
    if args.resume and progress_path.exists():
        raw = json.loads(progress_path.read_text(encoding="utf-8"))
        scenes = [Scene(**s) for s in raw["scenes"]]
        saved_job_name = raw.get("batch_job_name") or None
        log.info("Resumed with %d scenes (%d already done)%s",
                 len(scenes),
                 sum(1 for s in scenes if s.status in ("ok", "skipped")),
                 f", pending batch={saved_job_name}" if saved_job_name else "")
    else:
        split_model = PRO_MODEL if args.force_pro else FLASH_MODEL
        scenes = split_story(client, story, split_model)
        save_progress(progress_path, scenes)   # freeze split immediately

    if args.limit:
        scenes = scenes[:args.limit]

    # ── Batch pre-build all scene prompts (optional) ─────────────────────
    batch_results: dict[int, tuple[dict | None, str, str | None]] = {}
    if args.batch:
        batch_model = PRO_MODEL if args.force_pro else FLASH_MODEL
        try:
            if saved_job_name:
                log.info("Resuming batch job %s", saved_job_name)
                pending = [s for s in scenes
                           if s.status not in ("ok", "skipped")
                           and not s.prompt]
                job_name = saved_job_name
            else:
                job_name, pending = batch_create_scene_prompts(
                    client, scenes, characters, story, batch_model,
                )
                if job_name:
                    save_progress(progress_path, scenes,
                                  batch_job_name=job_name)
            if job_name:
                batch_results = batch_collect_scene_prompts(
                    client, job_name, pending, batch_model,
                )
                log.info("Batch finished: %d responses", len(batch_results))
                # Batch consumed — clear job name so resume won't re-pull it.
                save_progress(progress_path, scenes)
        except Exception as e:
            log.warning("Batch failed (%s), falling back to realtime", e)
            batch_results = {}

    # ── Process each scene ───────────────────────────────────────────────
    for scene in scenes:
        if scene.status in ("ok", "skipped"):
            continue

        log.info("── Scene %d/%d: %s", scene.index, len(scenes),
                 scene.title or scene.text[:60].replace("\n", " "))

        data: dict | None = None
        model: str = ""
        if scene.index in batch_results:
            data, model, berr = batch_results[scene.index]
            if berr:
                log.warning("Scene %d batch error (%s), retrying realtime",
                            scene.index, berr)
                data = None

        if data is None:
            try:
                data, model = build_scene_prompt(
                    client, scene, characters, story,
                    force_pro=args.force_pro,
                )
            except Exception as e:
                scene.status = "error"
                scene.error = f"prompt build failed: {e}"
                log.error(scene.error)
                save_progress(progress_path, scenes)
                continue

        scene.model_used = model
        scene.character_ids = list(data.get("existing_character_ids", []))
        new_chars = data.get("new_characters", [])
        base_prompt = data.get("prompt", "").strip()

        # ── Voice / subtitle metadata ────────────────────────────────────
        scene.voice_text = (data.get("voice_text") or scene.text).strip()
        scene.speaker = (data.get("speaker") or "narrator").strip()
        scene.emotion = (data.get("emotion") or "").strip()
        scene.pacing = (data.get("pacing") or "normal").strip()
        subs = data.get("subtitle_lines") or []
        scene.subtitle_lines = [str(s).strip() for s in subs if str(s).strip()]
        scene.duration_sec = estimate_duration(scene.voice_text, scene.pacing)

        # ── Handle new characters ────────────────────────────────────────
        added_any_new = False
        missing_refs = []
        for nc in new_chars:
            cid = nc["id"]
            if cid in characters:
                continue
            characters[cid] = {
                "name": nc["name"],
                "reference_image": f"references/{cid}.png",
                "description": nc["description"],
                "_auto_generated": True,
            }
            added_any_new = True
            missing_refs.append(cid)
            log.warning("NEW character '%s' added to %s — "
                        "reference image missing, please add "
                        "references/%s.png",
                        cid, chars_path.name, cid)

        if added_any_new:
            chars_path.write_text(
                json.dumps(characters, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        # ── Skip scene if any referenced character lacks a ref file ──────
        # (new auto-generated characters never have a ref yet)
        skip_reason = None
        if missing_refs:
            skip_reason = (f"new characters without reference: "
                           f"{', '.join(missing_refs)}")
        else:
            for cid in scene.character_ids:
                ref = Path(characters[cid].get("reference_image", ""))
                if not ref.exists():
                    skip_reason = f"reference image missing: {ref}"
                    break

        # Build final prompt
        scene.prompt = f"{base_prompt}\n\n{STYLE_SUFFIX}"

        if skip_reason:
            scene.status = "skipped"
            scene.error = skip_reason
            log.error("SKIP scene %d: %s", scene.index, skip_reason)
            save_progress(progress_path, scenes)
            continue

        if args.dry_run:
            scene.status = "ok"
            scene.image_path = ""
            log.info("[dry-run] prompt ready for scene %d", scene.index)
            save_progress(progress_path, scenes)
            continue

        # ── Image generation ─────────────────────────────────────────────
        ref_paths = [Path(characters[cid]["reference_image"])
                     for cid in scene.character_ids]
        img_path = out_dir / f"frame_{scene.index:03d}.png"
        ok = generate_image(client, scene.prompt, ref_paths, img_path)
        if ok:
            scene.status = "ok"
            scene.image_path = str(img_path)
            log.info("✓ saved %s", img_path)
        else:
            scene.status = "error"
            scene.error = "image generation failed"
        save_progress(progress_path, scenes)

    # ── Write final prompts.json ─────────────────────────────────────────
    prompts_path.write_text(
        json.dumps([asdict(s) for s in scenes],
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # ── Export SRT subtitles from finished scenes ────────────────────────
    try:
        export_srt(scenes, srt_path)
    except Exception as e:
        log.warning("SRT export failed: %s", e)

    log.info("Done. %d ok, %d skipped, %d error. Prompts: %s",
             sum(1 for s in scenes if s.status == "ok"),
             sum(1 for s in scenes if s.status == "skipped"),
             sum(1 for s in scenes if s.status == "error"),
             prompts_path)


def save_progress(path: Path, scenes: list[Scene],
                  batch_job_name: str | None = None):
    payload: dict[str, Any] = {"scenes": [asdict(s) for s in scenes]}
    if batch_job_name:
        payload["batch_job_name"] = batch_job_name
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
