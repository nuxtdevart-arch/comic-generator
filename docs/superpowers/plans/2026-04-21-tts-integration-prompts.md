# Gemini Prompts — TTS Integration Execution

Ready-to-paste prompts for executing the plan at `docs/superpowers/plans/2026-04-21-tts-integration.md`.

---

## Prompt for Task 1 — Env & Dependencies
```
Context: Read docs/superpowers/plans/2026-04-21-tts-integration.md Task 1.
Action: 
1. Create requirements-tts.txt with:
elevenlabs>=1.0.0
requests
2. Append placeholders for ELEVEN_API_KEY, YANDEX_API_KEY, YANDEX_FOLDER_ID to .env (if it exists).
3. Commit: "chore(deps): add TTS requirements and env placeholders"
```

## Prompt for Task 2 — voices.json
```
Context: Read docs/superpowers/specs/2026-04-21-tts-integration-design.md Section 3.1.
Action:
1. Create voices.json with basic config for "narrator" and "default".
2. Commit: "feat(tts): add initial voices.json"
```

## Prompt for Task 3 — Base TTS Utility
```
Context: Read generate_comic.py.
Action:
1. Implement get_voice_config and calculate_voice_hash in generate_comic.py.
2. Create tests/test_tts.py with basic unit tests for these.
3. Verify with pytest.
4. Commit: "feat(tts): implement voice config and hashing helpers"
```

## Prompt for Task 4 — ElevenLabs
```
Context: Read docs/superpowers/plans/2026-04-21-tts-integration.md Task 4.
Action:
1. Implement generate_elevenlabs_tts in generate_comic.py using the elevenlabs library.
2. Ensure it uses backoff_delay for retries on 429/5xx.
3. Commit: "feat(tts): implement ElevenLabs provider"
```

## Prompt for Task 5 — Yandex
```
Context: Read docs/superpowers/plans/2026-04-21-tts-integration.md Task 5.
Action:
1. Implement generate_yandex_tts in generate_comic.py using requests.
2. Commit: "feat(tts): implement Yandex SpeechKit provider"
```

## Prompt for Task 6 — Silero
```
Context: Read docs/superpowers/plans/2026-04-21-tts-integration.md Task 6.
Action:
1. Implement generate_silero_tts in generate_comic.py (lazy import torch).
2. Commit: "feat(tts): implement Silero local provider"
```

## Prompt for Task 7 — Pipeline Integration
```
Context: Read docs/superpowers/plans/2026-04-21-tts-integration.md Task 7.
Action:
1. Update argparse to include --tts and --voices.
2. Integrate generate_tts call into the main scene loop.
3. Implement the output/audio/ caching logic.
4. Commit: "feat(tts): integrate TTS into main pipeline"
```

## Prompt for Task 8 — Final Documentation & Smoke Test
```
Action:
1. Update TODO.md: mark Section 2 (TTS) as done.
2. Update CLAUDE.md: move TTS to Done and update Roadmap.
3. Update README.md: add documentation for --tts flag and voices.json.
4. Merge feature branch to master.
5. Commit: "docs: mark TTS integration complete"
```
