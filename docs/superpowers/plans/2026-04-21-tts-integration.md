# TTS Integration — Implementation Plan

**Goal:** Добавить поддержку TTS (ElevenLabs, Yandex, Silero) в пайплайн.

---

## Task 1: Environment & Dependencies
- [ ] **Step 1:** Create `requirements-tts.txt`.
- [ ] **Step 2:** Update `.env` with API keys placeholders.
- [ ] **Step 3:** Commit.

---

## Task 2: voices.json Skeleton
- [ ] **Step 1:** Create `voices.json` with a default narrator configuration.
- [ ] **Step 2:** Add basic character-to-voice mapping for the protagonist.
- [ ] **Step 3:** Commit.

---

## Task 3: Base TTS Utility
- [ ] **Step 1:** Implement `get_voice_config(speaker, voices_path)` helper.
- [ ] **Step 2:** Implement `calculate_voice_hash(text, config)` for caching.
- [ ] **Step 3:** Create `tests/test_tts.py` for these helpers.
- [ ] **Step 4:** Commit.

---

## Task 4: ElevenLabs Provider
- [ ] **Step 1:** Implement `generate_elevenlabs_tts(text, voice_config, out_path)`.
- [ ] **Step 2:** Add retry logic using `backoff_delay`.
- [ ] **Step 3:** Commit.

---

## Task 5: Yandex SpeechKit Provider
- [ ] **Step 1:** Implement `generate_yandex_tts(text, voice_config, out_path)`.
- [ ] **Step 2:** Commit.

---

## Task 6: Silero Provider (Optional/Local)
- [ ] **Step 1:** Implement `generate_silero_tts(text, voice_config, out_path)`.
- [ ] **Step 2:** Commit.

---

## Task 7: Pipeline Integration
- [ ] **Step 1:** Add `--tts` and `--voices` args to `argparse`.
- [ ] **Step 2:** Insert TTS generation call into the main scene loop in `generate_comic.py`.
- [ ] **Step 3:** Implement caching check before calling providers.
- [ ] **Step 4:** Commit.

---

## Task 8: Verification & Smoke Test
- [ ] **Step 1:** Run with `--tts elevenlabs --limit 1` (dry-run mode).
- [ ] **Step 2:** Verify `output/audio/scene_001.mp3` is created and playable.
- [ ] **Step 3:** Update `README.md` and `TODO.md`.
- [ ] **Step 4:** Final merge to master.
