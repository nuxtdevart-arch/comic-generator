# TTS Integration — Task-by-Task Execution Prompts

Ready-to-paste prompts for executing the plan at `docs/superpowers/plans/2026-04-21-tts-integration.md`. **One prompt per task.** Run sequentially; do not skip ahead.

**General rules baked into every prompt:**

1. Before doing anything, read the spec (`docs/superpowers/specs/2026-04-21-tts-integration-design.md`), the plan, and `CLAUDE.md` to ground yourself.
2. Execute only the current task's steps from the plan — do not touch tasks that come later.
3. Run every verification command in the task and paste the output before committing.
4. Do not invent steps the plan does not describe.
5. At the end of the task, report: files changed, test results, any deviations from the plan.

**Branching strategy:** one feature branch for the entire subproject, `feature/tts-integration`. The default branch is `master`. All task commits land on the feature branch; merge to `master` with `--no-ff` in Task 16 after the final smoke test passes.

**Remote:** `origin = https://github.com/nuxtdevart-arch/comic-generator.git` (public). Push only in Task 16 after the merge to master.

**Doc-sync:** deferred to Task 15 (docs) + Task 16 (merge). Intermediate tasks do not touch `README.md` / `TODO.md` / `CLAUDE.md`.

**⚠ Bootstrap state (already done before Task 1):**
- Branch `feature/tts-integration` exists and is checked out.
- Three prep commits on the branch (ahead of master):
  - `8878ca6` — initial (superseded) spec/plan/prompts.
  - `85663e3` — spec rewritten, old plan dropped.
  - `54f7126` — new implementation plan.
  - *this prompts file* — added after Task 15 completes.
- Working tree clean.

Proceed directly to Task 1.

---

## Prompt for Task 1 — Dependencies + .gitignore

```
Context to load first:
- Read CLAUDE.md.
- Read docs/superpowers/specs/2026-04-21-tts-integration-design.md, section 8.
- Read docs/superpowers/plans/2026-04-21-tts-integration.md, section "Task 1".

Your job: execute ONLY Task 1.

Steps:
1. Append `requests>=2.31` and `mutagen>=1.47` to requirements.txt.
2. Append `requests-mock>=1.11` to requirements-dev.txt.
3. Install both: `pip install -r requirements.txt -r requirements-dev.txt`.
4. Smoke-import: `python -c "import requests, mutagen, requests_mock; print('ok')"` — expect `ok`.
5. Add `output/audio/` line to .gitignore after `references/`.
6. Commit with the exact message from Task 1, Step 5.

Report:
- Output of smoke-import.
- Diff of requirements.txt, requirements-dev.txt, .gitignore.
- Commit hash.

Stop after Task 1.
```

---

## Prompt for Task 2 — voices.json skeleton

```
Context to load first:
- Read CLAUDE.md.
- Read docs/superpowers/specs/2026-04-21-tts-integration-design.md, section 3.1.
- Read docs/superpowers/plans/2026-04-21-tts-integration.md, section "Task 2".

Your job: execute ONLY Task 2.

Steps:
1. Create voices.json on the repo root with exactly the JSON shown in Task 2, Step 1. Do NOT invent additional per-character entries — MVP ships with narrator + default only.
2. Commit with the exact message from Task 2, Step 2.

Report:
- Content of voices.json.
- Commit hash.

Stop after Task 2.
```

---

## Prompt for Task 3 — tts.py skeleton + constants

```
Context to load first:
- Read CLAUDE.md.
- Read docs/superpowers/specs/2026-04-21-tts-integration-design.md, section 4.
- Read docs/superpowers/plans/2026-04-21-tts-integration.md, section "Task 3".

Your job: execute ONLY Task 3.

Steps:
1. Create tts.py on the repo root with the exact code from Task 3, Step 1 (imports + module-level constants + logger). Nothing else yet.
2. Smoke-import: `python -c "import tts; print(tts.DEFAULT_MODEL_ID)"` — expect `eleven_multilingual_v2`.
3. Commit with the exact message from Task 3, Step 3.

Do not add any function bodies — those belong to later tasks. Keep the file under 25 lines.

Report:
- Output of smoke-import.
- Content of tts.py.
- Commit hash.

Stop after Task 3.
```

---

## Prompt for Task 4 — load_voices (TDD)

```
Context to load first:
- Read CLAUDE.md.
- Read docs/superpowers/plans/2026-04-21-tts-integration.md, section "Task 4".
- Read existing tests/conftest.py (already adds repo root to sys.path — new tests just import tts).

Your job: execute ONLY Task 4. Strict TDD:

1. Create tests/test_tts.py with the `TestLoadVoices` class exactly as in Task 4, Step 1 (do not add other test classes yet).
2. Run tests, confirm all four FAIL because `load_voices` is undefined. Paste the failure output.
3. Append the `load_voices` implementation from Task 4, Step 3 to tts.py.
4. Run tests, confirm 4 pass. Paste output.
5. Commit with the exact message from Task 4, Step 5.

Do not implement resolve_voice, voice_hash, or anything else yet.

Report:
- Failing test output (Step 2).
- Passing test output (Step 4).
- Diff of tests/test_tts.py and tts.py.
- Commit hash.

Stop after Task 4.
```

---

## Prompt for Task 5 — resolve_voice (TDD)

```
Context to load first:
- Read CLAUDE.md.
- Read docs/superpowers/specs/2026-04-21-tts-integration-design.md, section 3.1 ("narrator" mandatory, fallback chain).
- Read docs/superpowers/plans/2026-04-21-tts-integration.md, section "Task 5".

Your job: execute ONLY Task 5. TDD.

Steps:
1. Append the `TestResolveVoice` class from Task 5, Step 1 to tests/test_tts.py (DO NOT rewrite — append).
2. Run the new class, confirm all tests FAIL with ImportError. Paste output.
3. Append the `resolve_voice` implementation from Task 5, Step 3 to tts.py.
4. Run the full test_tts file, confirm 10 pass (4 from Task 4 + 6 new). Paste output.
5. Commit with the exact message from Task 5, Step 5.

Watch-outs:
- Missing `narrator` raises ValueError (not KeyError).
- When the chosen entry omits `model_id`/`settings`, fall back to module-level DEFAULT_MODEL_ID / DEFAULT_SETTINGS.
- Settings from the entry REPLACE DEFAULT_SETTINGS entirely (not merge). Test `test_entry_fields_override_defaults` verifies this.

Report:
- Fail (Step 2) and pass (Step 4) outputs.
- Diff of tts.py + tests/test_tts.py.
- Commit hash.

Stop after Task 5.
```

---

## Prompt for Task 6 — voice_hash (TDD)

```
Context to load first:
- Read CLAUDE.md.
- Read docs/superpowers/specs/2026-04-21-tts-integration-design.md, section 3.3.
- Read docs/superpowers/plans/2026-04-21-tts-integration.md, section "Task 6".

Your job: execute ONLY Task 6. TDD.

Steps:
1. Append `TestVoiceHash` from Task 6, Step 1 to tests/test_tts.py.
2. Run, confirm FAIL (ImportError). Paste.
3. Append `voice_hash` from Task 6, Step 3 to tts.py.
4. Run full test_tts, confirm 17 pass. Paste.
5. Commit with message from Task 6, Step 5.

Watch-outs:
- Use `json.dumps(settings, sort_keys=True, ensure_ascii=True)` exactly. The key-reorder test depends on canonicalization.
- `voice_text.strip()` — trailing/leading whitespace must not change the hash (whitespace_trimmed test).

Report:
- Fail + pass outputs.
- Diff of tts.py + tests/test_tts.py.
- Commit hash.

Stop after Task 6.
```

---

## Prompt for Task 7 — audio_duration (mutagen)

```
Context to load first:
- Read CLAUDE.md.
- Read docs/superpowers/plans/2026-04-21-tts-integration.md, section "Task 7".

Your job: execute ONLY Task 7.

Steps:
1. Append `TestAudioDuration` from Task 7, Step 1 to tests/test_tts.py. This test SKIPS when `tests/fixtures/silence_1s.mp3` is absent — that's intentional. Do not create the fixture here; Task 14 handles it.
2. Run the test — it should either FAIL (function missing) or fail-then-skip. Paste.
3. Append `audio_duration` from Task 7, Step 3 to tts.py.
4. Run: test should skip (no fixture) or pass (if a local fixture already exists). 18 tests collected total. Paste.
5. Commit with message from Task 7, Step 5.

Report:
- Test outputs (Step 2 + Step 4).
- Diff.
- Commit hash.

Stop after Task 7.
```

---

## Prompt for Task 8 — generate_tts (HTTP + retry)

```
Context to load first:
- Read CLAUDE.md.
- Read docs/superpowers/specs/2026-04-21-tts-integration-design.md, section 5 (error classes + retry).
- Read docs/superpowers/plans/2026-04-21-tts-integration.md, section "Task 8".
- Read generate_comic.py lines 149-183 (classify_error, backoff_delay) to confirm the import path.

Your job: execute ONLY Task 8. HTTP logic with requests-mock. TDD.

Steps:
1. Append `TestGenerateTts` (including the autouse `no_sleep` fixture) from Task 8, Step 1 to tests/test_tts.py.
2. Run, confirm 4 FAIL (ImportError). Paste.
3. Append `_sleep` + `generate_tts` from Task 8, Step 3 to tts.py. Use the exact code — do NOT reorder the retry loop.
4. Add the `no_sleep` fixture as shown in Step 4 (inside the test class, autouse).
5. Run full test_tts, confirm 22 pass. Paste.
6. Commit with message from Task 8, Step 6.

Critical constraints:
- `classify_error` + `backoff_delay` are imported LAZILY inside generate_tts to avoid circular imports when generate_comic later imports tts.
- On non-200, convert to `RuntimeError(f"{status_code} {text[:200]}")` so classify_error's regex patterns match.
- On fatal (401/403/400/404), raise RuntimeError immediately — no retry.
- On retries exhausted, raise RuntimeError with the last error string.
- Atomic write: tmp path = `out_path.with_suffix(out_path.suffix + ".tmp")`, then `os.replace(tmp, out_path)`.
- Clean up tmp on error before raising.

Report:
- Fail + pass outputs.
- Diff of tts.py + tests/test_tts.py.
- Commit hash.

Stop after Task 8.
```

---

## Prompt for Task 9 — run_tts_stage

```
Context to load first:
- Read CLAUDE.md.
- Read docs/superpowers/specs/2026-04-21-tts-integration-design.md, section 5 (consecutive abort).
- Read docs/superpowers/plans/2026-04-21-tts-integration.md, section "Task 9".

Your job: execute ONLY Task 9. TDD with fake generate_tts.

Steps:
1. Append `FakeScene` dataclass and `TestRunTtsStage` class from Task 9, Step 1 to tests/test_tts.py.
2. Run new class, confirm 5 FAIL (ImportError). Paste.
3. Append `run_tts_stage` from Task 9, Step 3 to tts.py.
4. Run full test_tts, confirm 27 pass. Paste.
5. Commit with message from Task 9, Step 5.

Critical constraints:
- Skip logic: `scene.audio_hash == h AND out_path.exists()` → increment summary["skipped"], reset consecutive_errors, continue.
- Skip for empty voice_text: set audio_status="skipped", summary["skipped"]++, continue (NOT via cache hit).
- Scene whose `status != "ok"` is skipped silently (no counter bump).
- consecutive_errors increments on `resolve_voice` ValueError AND on `generate_tts` exceptions.
- consecutive_errors RESETS on successful generate_tts, and on cache-hit skip.
- On abort: set summary["aborted"]=True, return immediately, remaining scenes keep audio_status="pending".
- save_progress_fn() is called after each scene (including skips).

Report:
- Fail + pass outputs.
- Diff of tts.py + tests/test_tts.py.
- Commit hash.

Stop after Task 9.
```

---

## Prompt for Task 10 — Scene dataclass new fields

```
Context to load first:
- Read CLAUDE.md.
- Read docs/superpowers/specs/2026-04-21-tts-integration-design.md, section 3.2.
- Read docs/superpowers/plans/2026-04-21-tts-integration.md, section "Task 10".
- Read generate_comic.py lines 115-132 to confirm the current Scene dataclass.

Your job: execute ONLY Task 10.

Steps:
1. Replace the Scene dataclass block (lines 115-132) with the exact code from Task 10, Step 1. New fields append AFTER existing fields — preserves backward-compat with existing progress.json files.
2. Run full test suite: `pytest tests/test_pure.py tests/test_schemas.py tests/test_tts.py -v`. All must pass.
3. Smoke check: `python -c "from dataclasses import asdict; from generate_comic import Scene; s = Scene(index=1, text='x'); print(asdict(s))"` — expect dict with `audio_status='pending'`, `audio_duration=0.0`.
4. Commit with message from Task 10, Step 4.

Watch-out: do NOT reorder existing fields. New audio fields go at the END so positional usage and old progress.json files don't break.

Report:
- pytest output.
- Smoke output.
- Diff of generate_comic.py.
- Commit hash.

Stop after Task 10.
```

---

## Prompt for Task 11 — effective_duration + export_srt wiring

```
Context to load first:
- Read CLAUDE.md.
- Read docs/superpowers/specs/2026-04-21-tts-integration-design.md, section 6.
- Read docs/superpowers/plans/2026-04-21-tts-integration.md, section "Task 11".
- Read generate_comic.py lines 789-828 (export_srt + estimate_duration).

Your job: execute ONLY Task 11. TDD.

Steps:
1. Append `TestEffectiveDuration` from Task 11, Step 1 to tests/test_pure.py.
2. Run, confirm 4 FAIL (ImportError). Paste.
3. Add the `effective_duration` function from Task 11, Step 3 to generate_comic.py, placed IMMEDIATELY BEFORE `def export_srt(...)` (currently line 807). Replace the inline `scene.duration_sec or estimate_duration(...)` call in export_srt with `effective_duration(scene)` exactly as shown.
4. Run full pytest suite, confirm all pass. Paste.
5. Commit with message from Task 11, Step 5.

Watch-outs:
- Priority: audio_duration > duration_sec > estimate_duration. Task 11 tests verify audio_duration wins even when duration_sec is set.
- `scene.voice_text or scene.text` inside the fallback — preserves old behavior when voice_text empty.
- Do NOT delete or modify `estimate_duration` — effective_duration calls it.

Report:
- Fail (Step 2) and full-suite pass (Step 4) outputs.
- Diff of generate_comic.py + tests/test_pure.py.
- Commit hash.

Stop after Task 11.
```

---

## Prompt for Task 12 — CLI flags + TTS stage in main()

```
Context to load first:
- Read CLAUDE.md.
- Read docs/superpowers/specs/2026-04-21-tts-integration-design.md, section 4 (CLI) + section 5 (preflight).
- Read docs/superpowers/plans/2026-04-21-tts-integration.md, section "Task 12".
- Read generate_comic.py imports (top ~30 lines) and main() (lines 835-1085).

Your job: execute ONLY Task 12. Do NOT implement --tts-only behavior — that is Task 13.

Steps:
1. Add CLI args from Task 12, Step 1 after the existing `--verbose` arg. Three new args: `--tts`, `--tts-only`, `--voices`.
2. Add `import tts as tts_mod` to the import block (alongside the other top-level imports).
3. Add the preflight block from Task 12, Step 2 right after the `GEMINI_API_KEY` check in main(). This block sets `eleven_key` and `voices` when --tts/--tts-only, else both None.
4. Insert the TTS-stage block from Task 12, Step 3 BEFORE the `# ── Write final prompts.json ──` comment (currently line 1067), AFTER the main scene `for` loop completes.
5. Smoke (requires ELEVEN_API_KEY + story.txt + voices.json ready):
   ```
   python generate_comic.py --story story.txt --batch --dry-run --tts --limit 1
   ```
   Expected: preflight OK, TTS stage fires, one mp3 saved, progress.json shows audio_status=ok for scene 1.
6. Negative smoke: unset the key and rerun. Expect exit with "ERROR: ELEVEN_API_KEY not set in .env, required for --tts".
7. Commit with message from Task 12, Step 5.

Watch-outs:
- Preflight runs BEFORE the genai.Client is constructed — no point spending Gemini calls if TTS config is broken.
- `save_progress_fn` is a lambda closure over progress_path + scenes so run_tts_stage can persist after each scene.
- --tts-only branch is not yet handled in main(); a user running --tts-only here will still try to run the image stage. Acceptable until Task 13.

Report:
- Smoke outputs (both positive and negative).
- Tail of progress.json showing audio fields populated.
- Diff of generate_comic.py.
- Commit hash.

Stop after Task 12.
```

---

## Prompt for Task 13 — --tts-only standalone branch

```
Context to load first:
- Read CLAUDE.md.
- Read docs/superpowers/specs/2026-04-21-tts-integration-design.md, section 4 (--tts-only).
- Read docs/superpowers/plans/2026-04-21-tts-integration.md, section "Task 13".

Your job: execute ONLY Task 13.

Steps:
1. Change the `--story` argparse argument from `required=True` to `required=False, default=None` (so --tts-only users don't need story.txt).
2. Immediately after the story arg is parsed, add the guard from Task 13, Step 1:
   `if not args.tts_only and not args.story: sys.exit("ERROR: --story required unless --tts-only is set")`
3. After the preflight+voices block from Task 12, add the --tts-only early-return branch from Task 13, Step 1. This branch: loads progress.json, runs run_tts_stage, re-exports SRT, returns. NO image stage.
4. Smoke A (kache hit): with a prior successful --tts run present, run `python generate_comic.py --tts-only` — expect all scenes "skipped", no real HTTP calls (verify with --verbose).
5. Smoke B (error branch): temporarily delete an mp3, rerun --tts-only — expect 1 ok, 0 skipped for that scene, SRT updated.
6. Commit with message from Task 13, Step 3.

Watch-outs:
- --tts-only implies --tts (preflight fires for both).
- story.txt is loaded ONLY in the image-stage code path; --tts-only must return before that block.
- progress.json schema: `{"scenes": [{...dataclass fields...}], "batch_job_name": "..."}`. Load `data["scenes"]` and pass each dict to `Scene(**s)`.

Report:
- Smoke outputs for both A and B.
- Diff of generate_comic.py (main() only).
- Commit hash.

Stop after Task 13.
```

---

## Prompt for Task 14 — mp3 fixture (optional)

```
Context to load first:
- Read CLAUDE.md.
- Read docs/superpowers/plans/2026-04-21-tts-integration.md, section "Task 14".

Your job: execute ONLY Task 14 — OPTIONAL. Skip if ffmpeg is not installed on the machine.

Steps:
1. Check: `ffmpeg -version`. If missing, stop here — `test_reads_real_mp3` will remain skipped (that's fine, not a blocker for merge).
2. If ffmpeg present:
   ```
   mkdir -p tests/fixtures
   ffmpeg -f lavfi -i "anullsrc=r=44100:cl=mono" -t 1 -b:a 128k tests/fixtures/silence_1s.mp3 -y
   ```
3. Run: `pytest tests/test_tts.py::TestAudioDuration -v`. Expect 1 pass (no longer skip).
4. Commit with message from Task 14, Step 3.

Report:
- ffmpeg availability.
- Test output.
- Commit hash (if fixture was added) or "skipped — no ffmpeg".

Stop after Task 14.
```

---

## Prompt for Task 15 — Documentation sync (README + TODO + CLAUDE.md)

```
Context to load first:
- Read CLAUDE.md in full.
- Read README.md in full.
- Read TODO.md section 2 + the "Приоритеты" section.
- Read docs/superpowers/plans/2026-04-21-tts-integration.md, section "Task 15".

Your job: execute ONLY Task 15. Three doc files updated in ONE commit.

Part A — README.md:
1. Append a new "## TTS-озвучка (ElevenLabs)" section exactly as in Task 15, Step 1. Place it after the existing "## Устойчивость к сбоям" section (or wherever pipeline docs end — use judgement, but match existing style).

Part B — TODO.md section 2:
2. Replace the bullet list in section 2 exactly per Task 15, Step 2 (ElevenLabs items marked ✅, Yandex/Silero/emotion/normalization kept open).
3. In the "Приоритеты" section, mark item 1 (TTS) as ✅ with the April 2026 note.

Part C — CLAUDE.md:
4. In the "Архитектура" diagram, add the TTS stage line:
     `├─ TTS stage ────────► output/audio/scene_*.mp3 (ElevenLabs, --tts)`
5. In the "Главные функции" table, add a new row for `effective_duration`.
6. In the "Статус → ✅ Готово" section, add the TTS bullet per Task 15, Step 3.
7. In the "🚧 В работе (апрель 2026)" section, replace the current TTS-in-progress block with:
     "Нет активных подпроектов. Следующий — `--render-video` (TODO раздел 3)."
8. In the Roadmap list, mark item 1 (TTS) as ✅ completed with date; do NOT renumber remaining items.

Verify before commit:
- Run `pytest tests/ -v` — all green.
- Read the three doc files top-to-bottom, confirm formatting is consistent with existing style (Markdown headings, emoji, conventional order).

Commit with message from Task 15, Step 4.

Report:
- pytest output.
- Diffs of README.md, TODO.md, CLAUDE.md.
- Commit hash.

Stop after Task 15. Do not start Task 16 (merge) yet — user will review docs first.
```

---

## Prompt for Task 16 — End-to-end smoke + merge to master

```
Context to load first:
- Read CLAUDE.md (after Task 15 updates).
- Read docs/superpowers/plans/2026-04-21-tts-integration.md, section "Task 16".

Your job: final end-to-end verification + merge feature/tts-integration into master.

Part A — Full test suite:
1. Run: `pytest tests/ -v`. All green, including any previously skipped mp3 fixture test if Task 14 added the fixture.

Part B — End-to-end smoke with real API (requires ELEVEN_API_KEY + GEMINI_API_KEY):
2. Run: `python generate_comic.py --story story.txt --bootstrap --batch --tts --limit 1 --verbose`.
   Expected:
   - scene 1 gets both frame + mp3;
   - output/audio/scene_001.mp3 is playable (user verifies manually);
   - output/subtitles.srt first cue length matches mp3 within ±0.1s;
   - progress.json scene 1 has audio_status=ok, audio_hash, audio_duration filled.
3. Paste the tail of the run log (last ~30 lines) plus the first scene's entry from progress.json.

Part C — Idempotency:
4. Rerun the same command. Expect `TTS: 0 ok, 1 skipped, 0 error` — cache hit.

Part D — --tts-only smoke:
5. Run: `python generate_comic.py --tts-only --limit 1 --verbose`. Image stage must not fire; TTS stage cache-hits; SRT re-exported.

Part E — Merge to master:
6. Confirm clean tree: `git status`.
7. Inspect commit series: `git log --oneline master..HEAD`. Expect the 3 bootstrap docs commits + 1 commit per task (1-15, plus optional Task 14), ~16-17 commits total.
8. Switch to master: `git checkout master`.
9. Merge with `--no-ff`:
     git merge --no-ff feature/tts-integration -m "Merge feature/tts-integration: ElevenLabs TTS end-to-end"
10. Run `pytest tests/ -v` on master — all green.
11. Push master: `git push origin master`. If 403, stop and report.
12. Optionally push the feature branch for history: `git push -u origin feature/tts-integration`.
13. Do NOT delete the feature branch.

Verification:
- Paste: `git log --oneline --graph -25`.
- Paste: `git branch`.
- Paste: final `pytest tests/ -v`.
- Paste: `git push origin master` output.

Final report:
- Smoke results (frame generated, mp3 playable, SRT timing match).
- Total test count.
- All commit hashes from Task 1 onward (on feature branch), plus merge commit hash on master.
- Any deviations.

Stop. Subproject complete.
```

---

## Execution notes

**Order:** strictly 1 → 2 → ... → 16. Each prompt assumes prior tasks are complete and committed on `feature/tts-integration`.

**Between tasks:** review the agent's report (test output, diffs, commit hash). If anything deviated, fix before the next prompt.

**If the agent gets stuck:** do not let it invent workarounds. Stop, re-read the plan, adjust the prompt, rerun.

**Recovery:** if a task fails midway, `git reset --hard HEAD` (no commit yet) or `git reset --hard HEAD~1` (bad commit). Then rerun the prompt.

**Why docs are bundled into 15:**
- Until TTS-stage integration lands in main() (Task 12-13), updating README/TODO would describe vaporware.
- Task 15 fires after all code+tests land, so docs describe reality.
- Task 16 merges + pushes; doc diffs are part of the merge commit on master.

**Real API gates:** Tasks 12, 13, 16 require a live ELEVEN_API_KEY + GEMINI_API_KEY. Other tasks are offline (mocks). If the key is absent, stop at Task 12 and resume when the key is provisioned.
