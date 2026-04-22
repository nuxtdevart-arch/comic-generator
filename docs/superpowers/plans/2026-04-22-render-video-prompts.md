# `--render-video` — Task-by-Task Execution Prompts

Готовые promptы для пошагового выполнения плана `docs/superpowers/plans/2026-04-22-render-video.md`. **Один prompt на задачу.** Запускать строго последовательно; не прыгать вперёд.

**Общие правила, вшитые в каждый prompt:**

1. Перед чем-либо прочитать: spec (`docs/superpowers/specs/2026-04-22-render-video-design.md`), план (`docs/superpowers/plans/2026-04-22-render-video.md`), `CLAUDE.md`.
2. Выполнить ТОЛЬКО шаги текущей задачи из плана — не трогать следующие.
3. Прогнать каждую verification-команду и вставить вывод до коммита.
4. Не изобретать шаги, которых нет в плане.
5. В конце задачи отчитаться: какие файлы изменены, результат тестов, отклонения от плана.

**Branching:** одна feature-ветка на весь подпроект — `feature/render-video`. Default branch — `master`. Все task-коммиты ложатся на feature-ветку; merge в `master` с `--no-ff` выполняется в Task 12 после финального smoke test.

**Remote:** `origin = https://github.com/nuxtdevart-arch/comic-generator.git`. Push только в Task 12 после merge.

**Doc-sync стратегия:**
- **Task A (pre-work)**: ретрофит README — убрать устаревшие упоминания ручного TTS и ручной ffmpeg-склейки, которые противоречат уже смёрженной TTS-интеграции. Это расчистка перед началом работы над `--render-video`.
- **Task 11 (post-work)**: полный doc-sync для `--render-video` (README + TODO + CLAUDE.md). Здесь описываем новую фичу.
- **Промежуточные таски (0-10) не трогают** `README.md` / `TODO.md` / `CLAUDE.md`.

**Bootstrap state (выполнить до Task A):**
- Spec и plan уже закоммичены на `master` (коммиты `a99dd4c`, `fbb4a09`, `087957f`).
- Создать и зачекаутить ветку: `git checkout -b feature/render-video`.
- Working tree clean.

Приступаем с Task A.

---

## Prompt for Task A — README retrofit: убрать устаревшие TTS/ffmpeg-инструкции

```
Context to load first:
- Read CLAUDE.md.
- Read README.md in full, with particular attention to:
  - line ~24 ("Остаётся только: прогнать voice_text через TTS... и склеить ffmpeg'ом в видео с субтитрами.") — устарело, TTS автоматизирован.
  - lines ~195-212 (секция "### TTS (озвучка) — делаешь отдельно" + "### ffmpeg-склейка (пример)") — устарело, противоречит секции "## TTS-озвучка (ElevenLabs)" на ~232.
- Read existing "## TTS-озвучка (ElevenLabs)" section (~232-262) to понимать актуальный tone of voice.

Your job: ретрофит README. Убрать двойные/устаревшие инструкции. НЕ трогать ничего что связано с --render-video (это отдельная фича, для неё будет Task 11).

Steps:

1. Line ~24 ("Остаётся только: прогнать voice_text через TTS..."): заменить на краткую фразу, которая отражает реальность — TTS автоматизирован (флаг `--tts`), видеосборка пока вручную ffmpeg (временно, до `--render-video`). Пример замены:
   
   "TTS уже встроен — см. секцию TTS-озвучка ниже. Видеосборка пока через ffmpeg вручную (скоро будет `--render-video`)."

2. Секция "### TTS (озвучка) — делаешь отдельно" (строки ~195-203): удалить полностью. Она дублирует/противоречит уже существующей секции "## TTS-озвучка (ElevenLabs)".

3. Секция "### ffmpeg-склейка (пример)" (строки ~205-212): оставить, но добавить пометку в одну строку перед блоком: "Временно: пока нет `--render-video`, склейка руками:". (Этот пример полезен в переходный период. Когда Task 11 добавит render-video секцию, ffmpeg-пример можно будет удалить там же.)

4. Убедиться что после изменений README читается цельно сверху вниз: пайплайн работает end-to-end до TTS включительно, только финальная склейка в видео — временно вручную.

5. Запустить pytest tests/ -v — убедиться что изменения в README не ломают ничего (тесты README не импортят, но это sanity-чек).

6. Commit:

   git add README.md
   git commit -m "docs(readme): drop pre-TTS residuals (manual voice_text instructions)

After TTS integration merged, README had two contradictory sections
describing TTS — the old 'делаешь отдельно' block and the new
automated 'TTS-озвучка (ElevenLabs)' block. Removed the old block and
the now-misleading intro line. ffmpeg manual example kept with a
temporary note until --render-video ships."

Report:
- Diff of README.md.
- pytest output (tail).
- Commit hash.

Stop after Task A.
```

---

## Prompt for Task 0 — Pytest integration marker

```
Context to load first:
- Read CLAUDE.md.
- Read docs/superpowers/plans/2026-04-22-render-video.md, section "Task 0".
- Check: no existing pytest.ini / pyproject.toml / setup.cfg with pytest config (confirmed absent 2026-04-22).

Your job: execute ONLY Task 0.

Steps:
1. Create pytest.ini at repo root with the exact content from Task 0, Step 1 of the plan. Registers `integration` marker and auto-deselects integration tests by default (addopts = -m "not integration").
2. Run full test suite: pytest tests/ -v. Expect all existing tests (test_pure, test_schemas, test_tts) PASS. No integration tests exist yet, so marker has no effect but should not error.
3. Commit with the exact message from Task 0, Step 3.

Report:
- pytest output.
- Content of pytest.ini.
- Commit hash.

Stop after Task 0.
```

---

## Prompt for Task 1 — ASS time & color formatters (TDD)

```
Context to load first:
- Read CLAUDE.md.
- Read docs/superpowers/specs/2026-04-22-render-video-design.md, section "ASS-генерация".
- Read docs/superpowers/plans/2026-04-22-render-video.md, section "Task 1".
- Read existing tests/conftest.py (repo root on sys.path — new tests just import `video`).

Your job: execute ONLY Task 1. Strict TDD.

Steps:
1. Create tests/test_video.py with the TestFmtAssTime + TestHexToAssColor classes EXACTLY as in Task 1, Step 1 (включая модульный docstring).
2. Run: pytest tests/test_video.py -v. Confirm ImportError for `video` module. Paste output.
3. Create video.py at repo root with the exact imports, docstring, logger, и обе функции (`_fmt_ass_time`, `_hex_to_ass_color`) из Task 1, Step 3.
4. Run: pytest tests/test_video.py -v. Expect 13 tests PASS (7 time + 6 color + 1 error case, total 13). Paste output.
5. Commit with message from Task 1, Step 5.

Critical constraints:
- `_fmt_ass_time` uses centiseconds (cs = hundredths of a second), NOT milliseconds. `_fmt_srt_time` in generate_comic.py uses ms — do not copy that format.
- Rounding at `int(round(seconds * 100))` — test `59.999 -> "0:01:00.00"` proves rounding, not truncation.
- `_hex_to_ass_color` swaps RR↔BB (ASS uses &H00BBGGRR). Test вектор `#FF0000 -> &H000000FF` — красный становится low byte.
- Invalid hex raises ValueError (not RuntimeError, not KeyError).

Report:
- Failing test output (Step 2).
- Passing test output (Step 4).
- Diff of video.py and tests/test_video.py.
- Commit hash.

Stop after Task 1.
```

---

## Prompt for Task 2 — Quality presets + video hash

```
Context to load first:
- Read CLAUDE.md.
- Read docs/superpowers/specs/2026-04-22-render-video-design.md, section "Quality-пресеты" + section "Кэш".
- Read docs/superpowers/plans/2026-04-22-render-video.md, section "Task 2".

Your job: execute ONLY Task 2. TDD.

Steps:
1. Append `TestQualityPresets` + `TestComputeVideoHash` classes from Task 2, Step 1 to tests/test_video.py (DO NOT rewrite; append).
2. Run: pytest tests/test_video.py -v. Expect ImportError for QUALITY_PRESETS / compute_video_hash. Paste.
3. Append `QUALITY_PRESETS` constant + `compute_video_hash` function from Task 2, Step 3 to video.py. Add import `hashlib` и `from typing import Optional` в верх файла.
4. Run: pytest tests/test_video.py -v. Expect все тесты (старые + новые) PASS. Paste.
5. Commit with message from Task 2, Step 5.

Critical constraints:
- QUALITY_PRESETS["draft"] = {"res": (1280, 720), "fps": 24, "crf": 28, "preset": "ultrafast"} — exact values.
- QUALITY_PRESETS["final"] = {"res": (1920, 1080), "fps": 30, "crf": 18, "preset": "medium"} — exact values.
- compute_video_hash должен читать image_bytes и audio_bytes С ДИСКА каждый раз — это обеспечивает инвалидацию кэша при замене файла без изменения имени.
- audio_path может быть None (сценарий --allow-incomplete без аудио); в этом случае добавляем `b"<no-audio>"` в hash вместо файла.
- fps + resolution сериализуются как "{fps}|{W}x{H}" — не менять порядок, тесты его не проверяют но сохранённые в progress.json хеши сломаются при будущем изменении порядка.

Report:
- Fail (Step 2) and pass (Step 4) outputs.
- Diff of video.py + tests/test_video.py.
- Commit hash.

Stop after Task 2.
```

---

## Prompt for Task 3 — scene_ass_block (TDD)

```
Context to load first:
- Read CLAUDE.md.
- Read docs/superpowers/specs/2026-04-22-render-video-design.md, section "Dialogue события" (воспринять: subtitle_lines, НЕ voice_text; joiner = `\N`).
- Read docs/superpowers/plans/2026-04-22-render-video.md, section "Task 3".
- Read output/prompts.json для примера: у scene[0] voice_text ~400 символов, subtitle_lines = 3 строки. Понять разницу перед началом.

Your job: execute ONLY Task 3. TDD.

Steps:
1. Append TestSceneAssBlock to tests/test_video.py (append, не переписывать).
2. Run: pytest tests/test_video.py::TestSceneAssBlock -v. Expect ImportError. Paste.
3. Append `_escape_ass_text` + `scene_ass_block` from Task 3, Step 3 to video.py.
4. Run: pytest tests/test_video.py -v. Expect все тесты PASS. Paste.
5. Commit with message from Task 3, Step 5.

Critical constraints:
- Text source: subtitle_lines (JOIN with "\N"). Если subtitle_lines пустой — fallback на voice_text (одна длинная строка). Если и voice_text пустой — fallback на text.
- Эскейпить в тексте: `\` → `\\`, `{` → `\{`, `}` → `\}`. Порядок важен: сначала бэкслеш, потом скобки.
- Формат строки: `"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}"`. Без финального \n (block — одна логическая строка).
- В тестах используется динамический `type("S", (), dict)()` чтобы избежать зависимости от Scene dataclass — не меняй это.

Report:
- Fail (Step 2) and pass (Step 4) outputs.
- Diff.
- Commit hash.

Stop after Task 3.
```

---

## Prompt for Task 4 — export_ass (TDD)

```
Context to load first:
- Read CLAUDE.md.
- Read docs/superpowers/specs/2026-04-22-render-video-design.md, section "Маппинг design_spec.json → ASS" (особенно таблица с ключами реального design_spec.json).
- Read docs/superpowers/plans/2026-04-22-render-video.md, section "Task 4".
- Read output/design_spec.json для реальных ключей: font_family, font_size_px, color_fg, stroke_color, stroke_px, position="bottom_centered", margin_bottom_pct.

Your job: execute ONLY Task 4. TDD.

Steps:
1. Append TestExportAss to tests/test_video.py.
2. Run: pytest tests/test_video.py::TestExportAss -v. Expect ImportError.
3. Append `_POSITION_TO_ALIGNMENT`, `_style_line_from_spec`, `_ASS_HEADER_TEMPLATE`, `export_ass` from Task 4, Step 3 to video.py.
4. Run: pytest tests/test_video.py -v. Expect все тесты PASS.
5. Commit with message from Task 4, Step 5.

Critical constraints:
- MarginV = int(resolution[1] * margin_bottom_pct / 100). Тест ожидает 86 для (1920,1080) × 8% — не округляй в сторону 87.
- Alignment numpad: bottom_centered → 2. Map включает alias'ы (`bottom_center`, `bottom-center`) чтобы стерпеть вариации в design_spec.
- Секции идут строго в порядке: [Script Info] → [V4+ Styles] → [Events]. Format-строки V4+ Styles и Events ДОЛЖНЫ совпадать с полями Style/Dialogue по числу и порядку.
- export_ass фильтрует сцены со status != "ok" (как export_srt в generate_comic.py). Durations-массив соответствует сценам as-passed — если сцена со status="error" попала в список, её duration всё равно в durations, но она не появится в Events (accurate mirror of export_srt logic). Тест `test_skips_non_ok_scenes` это проверяет.
- Cursor (накопительная сумма) — суммируем durations ТОЛЬКО для сцен co status="ok". Перепиши логику, если в плановом коде это не так.

Watch-out:
- Плановый код в Task 4, Step 3 использует `for scene, dur in zip(scenes, effective_durations)` и фильтрует статус ВНУТРИ цикла — значит cursor ведёт себя как надо (dur добавляется только для ok-сцен). Это нормально, не переписывай.

Report:
- Fail / pass outputs.
- Diff.
- Commit hash.

Stop after Task 4.
```

---

## Prompt for Task 5 — check_ffmpeg + probe_audio_duration

```
Context to load first:
- Read CLAUDE.md.
- Read docs/superpowers/plans/2026-04-22-render-video.md, section "Task 5".
- Verify: `ffmpeg -version` и `ffprobe -version` на машине (Gyan.FFmpeg.Essentials установлен, проверено 2026-04-22).

Your job: execute ONLY Task 5. TDD с unittest.mock.

Steps:
1. Append TestCheckFfmpeg + TestProbeAudioDuration from Task 5, Step 1 to tests/test_video.py. Добавь `from unittest.mock import patch, MagicMock` в импорты файла (если ещё нет).
2. Run: pytest tests/test_video.py::TestCheckFfmpeg tests/test_video.py::TestProbeAudioDuration -v. Expect ImportError.
3. Add imports `import shutil`, `import subprocess` в верх video.py. Append `check_ffmpeg` + `probe_audio_duration` from Task 5, Step 3.
4. Run: pytest tests/test_video.py -v. Expect все тесты PASS.
5. Commit with message from Task 5, Step 5.

Critical constraints:
- check_ffmpeg использует `shutil.which` (кросс-платформенно, Windows-friendly). НЕ shell=True.
- probe_audio_duration читает только format=duration (одно число на stdout), parse через `float(stdout.strip())`.
- Ошибка возврата (returncode != 0) → RuntimeError с stderr в сообщении.
- Отсутствие файла (до вызова ffprobe) → FileNotFoundError (явный — проверка Path.exists()).

Report:
- Fail / pass outputs.
- Diff.
- Commit hash.

Stop after Task 5.
```

---

## Prompt for Task 6 — Scene dataclass extension (video fields)

```
Context to load first:
- Read CLAUDE.md.
- Read docs/superpowers/plans/2026-04-22-render-video.md, section "Task 6".
- Read generate_comic.py lines 116-139 (current Scene dataclass — с TTS-полями в конце).

Your job: execute ONLY Task 6.

Steps:
1. Append TestSceneVideoFields class from Task 6, Step 1 to tests/test_video.py.
2. Run: pytest tests/test_video.py::TestSceneVideoFields -v. Expect AssertionError — полей video_* нет в Scene.
3. Extend Scene dataclass in generate_comic.py: ПОСЛЕ строки 139 (`audio_error: str = ""`), ВНУТРИ @dataclass class Scene:, добавить 4 поля из Task 6, Step 3. Новые поля идут В КОНЕЦ — preserve backward-compat с существующим output/progress.json.
4. Run: pytest tests/test_video.py::TestSceneVideoFields tests/test_schemas.py tests/test_pure.py -v. Ожидание: все PASS.
5. Smoke: backward-compat со старым progress.json.
   
   Run (Windows bash/Git Bash):
     PYTHONIOENCODING=utf-8 python -c "import json; from generate_comic import Scene; d=json.load(open('output/progress.json',encoding='utf-8')); scenes=[Scene(**s) for s in d['scenes']]; print(f'Loaded {len(scenes)} scenes, video_path[0]={scenes[0].video_path!r}')"
   
   Expected: без ошибок, `video_path=''`.
6. Commit with message from Task 6, Step 6.

Critical constraints:
- Порядок полей имеет значение: новые video_* строго ПОСЛЕ всех TTS-полей (audio_*). Старые progress.json передают scene dict через **kwargs — если вставить в середине, Python не сломается (kwargs по имени), но визуально ломается чтение diff'ов.
- Не менять существующие поля. Не менять их defaults.
- default для video_status = "pending" (а не "ok") — иначе сцены без video будут трактоваться как уже отрендеренные.

Report:
- Fail (Step 2) / full-suite pass (Step 4) outputs.
- Smoke output (Step 5).
- Diff of generate_comic.py + tests/test_video.py.
- Commit hash.

Stop after Task 6.
```

---

## Prompt for Task 7 — render_scene_video + integration smoke

```
Context to load first:
- Read CLAUDE.md.
- Read docs/superpowers/specs/2026-04-22-render-video-design.md, section "Per-scene ffmpeg команда" + "Per-scene ffmpeg ошибки" + "Атомарность".
- Read docs/superpowers/plans/2026-04-22-render-video.md, section "Task 7".
- Verify real assets exist: `ls output/frame_001.png output/audio/scene_001.mp3 output/design_spec.json output/progress.json`.

Your job: execute ONLY Task 7. TDD + integration smoke на реальных ассетах.

Steps:

Part A — unit tests с mock subprocess:
1. Append TestRenderSceneVideo class from Task 7, Step 1 to tests/test_video.py.
2. Run: pytest tests/test_video.py::TestRenderSceneVideo -v. Expect ImportError / AttributeError (нет render_scene_video / VIDEO_MAX_RETRIES).

Part B — integration smoke:
3. Create tests/test_video_integration.py with content from Task 7, Step 2 EXACTLY. Файл начинается с `pytestmark = pytest.mark.integration` — весь файл скипается по умолчанию.

Part C — implementation:
4. Add `import time` в верх video.py. Append `VIDEO_MAX_RETRIES`, `VIDEO_RETRY_BACKOFF`, `_build_ffmpeg_cmd`, `render_scene_video` from Task 7, Step 3 to video.py.

Part D — verification:
5. Run unit tests: pytest tests/test_video.py -v. Expect все PASS (включая TestRenderSceneVideo).
6. Run integration smoke: pytest -m integration tests/test_video_integration.py -v. Expect PASS. Файл сценария: реальный ffmpeg создаёт `tests/tmp/.../scene_001.mp4` на основе `output/frame_001.png` + `output/audio/scene_001.mp3`, ffprobe возвращает h264/1280×720.
7. Commit with message from Task 7, Step 6.

Critical constraints:
- ASS filter на Windows: путь в vf ДОЛЖЕН быть через прямые слэши (`str(ass_path).replace("\\", "/")`). Обратные слэши в строке фильтра ломают libass.
- Atomic write: сначала пишем в `scene_NNN.mp4.tmp`, после успеха — `out_tmp.replace(out_mp4)`. НЕ использовать shutil.move.
- Retry: 3 попытки, backoff из VIDEO_RETRY_BACKOFF = [2.0, 8.0]. После третьего фейла — RuntimeError, scene.video_status="error", .video_error = последний stderr.
- Hash-кэш: проверка `scene.video_hash == expected_hash AND out_mp4.exists() AND scene.video_status == "ok"`. Все три условия.
- Cleanup: .tmp удаляется между попытками при fail (чтобы следующий attempt не принял чужой полу-файл за результат).

Watch-out (Windows-specific):
- Если integration smoke падает с "unable to open file" — проверь что ffmpeg callable (где-то проскакивает `where ffmpeg.exe` при необходимости). Первая же попытка должна упасть на check_ffmpeg если бинарь недоступен.

Report:
- Fail output (Step 2).
- Unit test pass output (Step 5).
- Integration smoke pass output (Step 6) — особенно размер созданного mp4 и ffprobe-вывод.
- Diff of video.py + tests/test_video.py + tests/test_video_integration.py.
- Commit hash.

Stop after Task 7.
```

---

## Prompt for Task 8 — concat_scenes

```
Context to load first:
- Read CLAUDE.md.
- Read docs/superpowers/specs/2026-04-22-render-video-design.md, section "Concat команда".
- Read docs/superpowers/plans/2026-04-22-render-video.md, section "Task 8".

Your job: execute ONLY Task 8. TDD с mock subprocess.

Steps:
1. Append TestConcatScenes class from Task 8, Step 1 to tests/test_video.py.
2. Run: pytest tests/test_video.py::TestConcatScenes -v. Expect ImportError.
3. Append `concat_scenes` from Task 8, Step 3 to video.py.
4. Run: pytest tests/test_video.py -v. Expect 3 новых теста PASS (все остальные тоже PASS).
5. Commit with message from Task 8, Step 5.

Critical constraints:
- concat demuxer format `ffconcat version 1.0` + строки `file '<path>'` — path в одиночных кавычках, с прямыми слэшами (см. Task 7 для обоснования).
- Команда: `ffmpeg -y -f concat -safe 0 -i <list.txt> -c copy <output>`. `-c copy` критично — это склейка без перекодирования, не ресемплит аудио.
- Пустой список сцен → ValueError("Cannot concat: no scenes provided"). НЕ RuntimeError.
- Ошибка ffmpeg → RuntimeError с последней строкой stderr. Файл list.txt остаётся на диске (полезен для отладки).
- Atomic write для final output: .mp4.tmp → replace, как в Task 7.

Report:
- Fail / pass outputs.
- Diff.
- Commit hash.

Stop after Task 8.
```

---

## Prompt for Task 9 — render_video orchestrator

```
Context to load first:
- Read CLAUDE.md.
- Read docs/superpowers/specs/2026-04-22-render-video-design.md, section "Fail-fast предусловия" + "Идемпотентность".
- Read docs/superpowers/plans/2026-04-22-render-video.md, section "Task 9".
- Read generate_comic.py lines 796-826 (estimate_duration + effective_duration — мы должны зеркалить логику в video-пайплайне).

Your job: execute ONLY Task 9. TDD с mock ffmpeg.

Steps:
1. Append TestRenderVideoOrchestrator class from Task 9, Step 1 to tests/test_video.py.
2. Run: pytest tests/test_video.py::TestRenderVideoOrchestrator -v. Expect ImportError.
3. Append `_effective_duration_for_video` + `render_video` from Task 9, Step 3 to video.py.
4. Run: pytest tests/test_video.py -v. Expect все PASS.
5. Commit with message from Task 9, Step 5.

Critical constraints:
- Fail-fast order: check_ffmpeg → quality validation → per-scene asset check → render.
- allow_incomplete=False: первая сцена с отсутствующим image/audio → RuntimeError на этом месте, ДО вызовов ffmpeg.
- allow_incomplete=True: сцена помечается video_status="skipped", в renderable не попадает.
- _effective_duration_for_video: приоритет audio_duration > duration_sec > estimate_duration. LAZY-import estimate_duration из generate_comic (избегаем циклический импорт).
- export_ass получает ТОЛЬКО renderable сцены с соответствующими durations (иначе несинхрон между видео и субтитрами).
- save_progress_fn вызывается после КАЖДОЙ сцены (success ИЛИ fail) — потеря работы при прерывании минимальна.
- Итоговый concat запускается только если mp4s непустой. Если все сцены провалились — RuntimeError.

Watch-out:
- Тест `test_idempotent_second_run` проверяет: второй запуск → 1 call_log entry (только concat). Если per-scene ffmpeg вызывается повторно — баг в hash-cache.

Report:
- Fail / pass outputs.
- Diff.
- Commit hash.

Stop after Task 9.
```

---

## Prompt for Task 10 — CLI integration (flags + stages)

```
Context to load first:
- Read CLAUDE.md.
- Read docs/superpowers/specs/2026-04-22-render-video-design.md, section "CLI флаги".
- Read docs/superpowers/plans/2026-04-22-render-video.md, section "Task 10".
- Read generate_comic.py:
  - строки ~884-886 (текущий последний argparse arg `--voices`) — новые флаги вставлять сразу после;
  - строки ~927-970 (блок `if args.tts_only:`) — образец "early return" стадии;
  - конец main() (поиск `export_srt(scenes, srt_path)`) — точка вставки autostage.

Your job: execute ONLY Task 10. Live integration с реальными output/ ассетами.

Steps:

Part A — argparse flags:
1. Add 5 новых argparse args из Task 10, Step 1 СРАЗУ ПОСЛЕ строки `ap.add_argument("--voices", ...)`.

Part B — story-required guard:
2. Update the existing guard (строка ~888):
   old: `if not args.tts_only and not args.story:`
   new: `if not (args.tts_only or args.render_video_only) and not args.story:`
   Также обновить сообщение об ошибке, упомянув `--render-video-only`.

Part C — render-video-only early path:
3. Найти конец блока `if args.tts_only:` (ищи закрывающую скобку/возврат). СРАЗУ ПОСЛЕ него добавить блок `if args.render_video_only:` из Task 10, Step 3. ВАЖНО: import `video as video_mod` внутри блока (lazy), а не в top-level imports — избегаем загрузку на каждом запуске.

Part D — render-video autostage:
4. Найти финальный `export_srt(scenes, srt_path)` в конце main() (в потоке после TTS-стадии, перед `return` или концом функции). СРАЗУ ПОСЛЕ export_srt добавить блок `if args.render_video:` из Task 10, Step 4. Та же lazy-import.

Part E — verification:
5. Smoke CLI parsing:
   python generate_comic.py --help 2>&1 | grep -E "render-video|quality|allow-incomplete|^\s+--output"
   Expected: 5 new flags visible (`--render-video`, `--render-video-only`, `--quality`, `--output`, `--allow-incomplete`).

6. Smoke render-video-only на real output/ (требует ffmpeg + существующих ассетов):
   rm -f output/comic.mp4 output/subtitles.ass
   rm -rf output/video/
   python generate_comic.py --render-video-only --quality draft --allow-incomplete --output output/comic_test.mp4 2>&1 | tail -30
   
   Expected logs: "Render-video-only stage", per-scene "🎬 scene N rendered in X.Xs" для каждой ok-сцены, "🎞️  final video → output/comic_test.mp4".
   
   Проверить:
   ls -la output/comic_test.mp4 output/video/scene_*.mp4 | head -10
   ffprobe -v error -show_entries format=duration output/comic_test.mp4
   
   Ожидаемая длительность ≈ sum audio_duration всех ok-сцен. Открыть файл в плеере — визуально проверить что субтитры видны, аудио синхронно.

7. Smoke idempotency: повторить команду из Step 6. Expected: "🎬 scene N: cached, skip" для всех сцен, только concat пересобирается. Run time < 10s.

8. Smoke quality switch:
   python generate_comic.py --render-video-only --quality final --allow-incomplete --output output/comic_final.mp4 2>&1 | tail -10
   
   Expected: все сцены пересобираются (hash изменился из-за quality). ffprobe на output/comic_final.mp4 должен показать width=1920, height=1080.

9. Commit:
   git add generate_comic.py
   git commit -m "feat(cli): --render-video / --render-video-only / --quality / --output"

Critical constraints:
- Lazy import `video` внутри if-блоков (не в top-level) — модуль нужен только когда флаг использован.
- Оба пути (autostage и standalone) реюзают ОДНУ функцию video_mod.render_video(...). Не копировать логику.
- save_progress_fn — lambda closure на progress_path + scenes (паттерн как в TTS stage).
- При ошибке (RuntimeError) в standalone-ветке: sys.exit(f"ERROR: {e}"). В autostage: log.error и continue (не прерывать если юзер потратил деньги на весь пайплайн).

Watch-out:
- Если rm команды не отработали на Windows (конфликт прав) — удалить ручками через explorer перед Step 6.
- comic_test.mp4 / comic_final.mp4 / subtitles.ass / video/*.mp4 — добавить в .gitignore если ещё нет (они в output/, но доп-проверка не помешает).

Report:
- --help output (Step 5).
- Tail of render-video-only smoke run (Step 6) + ffprobe duration.
- Tail of idempotent re-run (Step 7) — должно быть только concat.
- ffprobe resolution от final quality run (Step 8).
- Diff of generate_comic.py (только main() + argparse).
- Commit hash.

Stop after Task 10.
```

---

## Prompt for Task 11 — Documentation sync (README + TODO + CLAUDE.md)

```
Context to load first:
- Read CLAUDE.md in full (после Task A — устаревшие фрагменты уже убраны).
- Read README.md in full.
- Read TODO.md (особенно раздел 3 "Видеосборка" и раздел "Приоритеты").
- Read docs/superpowers/plans/2026-04-22-render-video.md, section "Task 11".

Your job: execute ONLY Task 11. Три doc-файла в ОДНОМ коммите.

Part A — README.md:
1. Append a new "### --render-video / --render-video-only — финальный mp4" section EXACTLY as in Task 11, Step 1 plan. Место вставки: СРАЗУ после секции "## TTS-озвучка (ElevenLabs)" (~строка 262), ДО секции "## Устойчивость к сбоям" (если та идёт позже) или до конца файла. Match existing markdown style.
2. Удалить временный комментарий "Временно: пока нет --render-video..." из Task A (он был добавлен как переходный). Также удалить блок "### ffmpeg-склейка (пример)" — теперь его заменяет `--render-video`.
3. Проверить line ~24 ("TTS уже встроен... скоро будет --render-video") — заменить на актуальную формулировку: "TTS и видеосборка встроены — см. разделы `--tts` и `--render-video` ниже."

Part B — TODO.md:
4. Раздел 3 ("Видеосборка"): заменить bullet list EXACTLY как в Task 11, Step 2 плана. Первые два пункта — ✅ с датой 2026-04-22, остальные (Ken Burns, crossfade, BGM, 9:16) остаются открытыми.
5. Раздел "Приоритеты" (в самом низу): обновить пункт 2 — `✅ **--render-video** (пункт 3) — финальный mp4 одной командой (апрель 2026).` Оставшиеся пункты (сейчас 3, 4, 5) НЕ перенумеровывать.

Part C — CLAUDE.md:
6. Секция "Архитектура" → диаграмма пайплайна: добавить строку рендера после TTS:
     └─ Video render ─────► output/comic.mp4 (--render-video, ffmpeg)
   (Заменить предыдущую `└─ SRT export ...` на `├─ SRT export ...` и новая `└─ Video render ...` последней.)
7. Секция "Главные функции": добавить 5 строк (video.check_ffmpeg, video.export_ass, video.render_scene_video, video.concat_scenes, video.render_video) — таблица из Task 11, Step 3.
8. Секция "Статус → ✅ Готово": добавить bullet про видеосборку из Task 11, Step 3.
9. Секция "🚧 В работе (апрель 2026)": заменить блок "Следующий — --render-video" на "Нет активных подпроектов. Следующий — `--scene N` + параллельная генерация (TODO раздел 1)."
10. Секция "Roadmap": пункт 2 помечаем ✅ с датой 2026-04-22. НЕ перенумеровывать оставшиеся.
11. Секция "Частые команды": добавить два примера из Task 11, Step 3 плана.

Part D — verification:
12. Run: pytest tests/ -v — всё зелёное.
13. Прочитать все три файла top-to-bottom: markdown должен быть валиден (правильные уровни заголовков, emoji, порядок секций совпадает с существующим стилем).
14. Commit:
    git add README.md TODO.md CLAUDE.md
    git commit -m "docs(render-video): README/TODO/CLAUDE.md updates after --render-video ships"

Report:
- pytest output.
- Diffs of README.md, TODO.md, CLAUDE.md.
- Commit hash.

Stop after Task 11. Do not start Task 12 (merge) yet — пользователь сначала ревьюит doc-дифф.
```

---

## Prompt for Task 12 — End-to-end smoke + merge to master

```
Context to load first:
- Read CLAUDE.md (после Task 11 обновлений).
- Read docs/superpowers/plans/2026-04-22-render-video.md, section "Task 12".

Your job: финальная end-to-end верификация + merge `feature/render-video` в `master`.

Part A — Полный test suite:
1. Run: pytest tests/ -v. Все зелёные (integration тесты скипаются по default).
2. Run integration: pytest -m integration tests/test_video_integration.py -v. Expect PASS (real ffmpeg работает).

Part B — Full render-video smoke на real ассетах:
3. Clean prior runs:
   rm -f output/comic.mp4 output/subtitles.ass
   rm -rf output/video/
4. Run draft render:
   python generate_comic.py --render-video-only --quality draft --allow-incomplete
   Expected:
   - output/subtitles.ass создан;
   - output/video/scene_NNN.mp4 для каждой ok-сцены с image+audio;
   - output/comic.mp4 создан.
5. ffprobe length check:
   ffprobe -v error -show_entries format=duration output/comic.mp4
6. Открыть output/comic.mp4 в плеере: субтитры видны, аудио синхронно, hard-cut между сценами ожидаем (MVP).

Part C — Idempotency:
7. Rerun Step 4 команду. Expected: per-scene cached ("🎬 scene N: cached, skip"), только concat. Run time < 10s.

Part D — Quality switch:
8. Run final quality:
   python generate_comic.py --render-video-only --quality final --allow-incomplete --output output/comic_final.mp4
   Expected: все сцены пересобираются. ffprobe на output/comic_final.mp4 → width=1920, height=1080.

Part E — Autostage smoke (real API, требует GEMINI + ELEVEN keys):
9. (Опционально, если ключи доступны и не жалко денег на 1 сцену):
   python generate_comic.py --story story.txt --batch --tts --render-video --limit 1 --verbose
   Expected: image + TTS + video все работают в одном запуске.
   
   Если пропускаем Part E — явно указать в отчёте.

Part F — Merge to master:
10. Confirm clean tree: git status.
11. Inspect commit series: git log --oneline master..HEAD. Ожидаемо ~13 коммитов (Task A + Task 0..11, всего 13).
12. Switch to master: git checkout master.
13. Merge с --no-ff:
    git merge --no-ff feature/render-video -m "Merge feature/render-video: ffmpeg-based --render-video end-to-end"
14. Run pytest tests/ -v на master — все зелёные.
15. Push master: git push origin master. Если 403 — stop and report.
16. Push feature branch для истории: git push -u origin feature/render-video.
17. НЕ удалять feature ветку.

Verification:
- Paste: git log --oneline --graph -20.
- Paste: git branch.
- Paste: финальный pytest tests/ -v.
- Paste: git push output.

Final report:
- Smoke results (draft + final + idempotency).
- Observable duration comic.mp4.
- Subtitles видимость + аудио синхрон (ручная проверка).
- Total test count.
- Hash каждого коммита (Task A + Tasks 0..11) на feature + merge hash на master.
- Отклонения от плана.

Stop. Subproject complete.
```

---

## Execution notes

**Order:** строго A → 0 → 1 → ... → 12. Каждый prompt предполагает что предыдущие таски выполнены и закоммичены на `feature/render-video`.

**Между тасками:** ревьюить отчёт агента (test output, diffs, commit hash). При отклонении — чинить до следующего prompt.

**Если агент застрял:** не давай ему изобретать workarounds. Останови, перечитай план, скорректируй prompt, запусти заново.

**Recovery:** если таск упал посредине — `git reset --hard HEAD` (если не закоммитили) или `git reset --hard HEAD~1` (если коммит bad). Затем перезапусти prompt.

**Почему Task A идёт первой:**
- README после merge tts-integration содержит двойные/устаревшие инструкции про TTS и ffmpeg. Это создаёт шум и противоречия для любого, кто попытается следовать документации сейчас.
- Очистка README ДО начала новой фичи = чистый старт. Когда Task 11 добавит секцию про `--render-video`, документ останется связным.

**Почему docs bundled в Task 11:**
- До Task 10 (CLI интеграция) флаг `--render-video` не работает. Документация о нерабочей фиче = vaporware.
- Task 11 срабатывает после всего кода + тестов: docs описывают реальность.
- Task 12 merge + push; doc-диффы уходят в merge commit.

**Real-dependency gates:**
- Tasks 7, 10, 12 требуют живой ffmpeg + ffprobe и реальных `output/frame_*.png`, `output/audio/scene_*.mp3`, `output/design_spec.json`, `output/progress.json`.
- Task 12 Part E (опционально) требует ELEVEN_API_KEY + GEMINI_API_KEY — если ключей нет, пропустить с явной пометкой.
- Остальные таски — offline (unit-тесты + mock subprocess).
