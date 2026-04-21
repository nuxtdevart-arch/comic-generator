# Gemini Prompts — Task-by-Task Execution

Ready-to-paste prompts for executing the plan at `docs/superpowers/plans/2026-04-21-tests-schema-validation.md` with a Gemini-based agent. **One prompt per task.** Run sequentially; do not skip ahead.

**General rules baked into every prompt:**

1. Before doing anything, read the spec (`docs/superpowers/specs/2026-04-21-tests-schema-validation-design.md`), the plan, and `CLAUDE.md` to ground yourself.
2. Execute only the current task's steps from the plan — do not touch tasks that come later.
3. Run every verification command in the task and paste the output before committing.
4. Do not invent steps the plan does not describe.
5. At the end of the task, report: files changed, test results, any deviations from the plan.

Doc-sync tasks (TODO.md, CLAUDE.md, README.md) are bundled into Task 11 (pure tests milestone) and Task 18 (final milestone). Intermediate tasks do not touch docs.

**Branching strategy:** one feature branch for the entire subproject, named `feature/tests-schema-validation`. Created in Task 0 after `git init`, all 18 task commits land on it, merged back to `main` in Task 18 after the final smoke test passes. Do NOT create a branch per task — commits are atomic enough on their own.

---

## Prompt for Task 0 — Git init + gitignore

```
You are working in the Comic Frame Generator repository at the current working directory. The project is not yet under version control.

Context to load first:
- Read CLAUDE.md (project architecture, conventions, status).
- Read docs/superpowers/plans/2026-04-21-tests-schema-validation.md, section "Task 0".
- Read docs/superpowers/specs/2026-04-21-tests-schema-validation-design.md (background context).

Your job: execute ONLY Task 0 of the plan. Do not advance to later tasks.

Steps to perform:
1. Run: git init && git branch -M main
2. Create .gitignore with exactly the contents specified in the plan's Task 0, Step 2. Do not invent extra entries.
3. Stage the listed files and make the initial commit with the exact message from Step 3 on main.
4. Create and switch to the feature branch: git checkout -b feature/tests-schema-validation
   (All subsequent tasks 1-17 commit on this branch. Task 18 merges it back to main.)

Verification:
- Run: git log --oneline
  Expected: exactly one commit named "chore: initial repo with existing script".
- Run: git status
  Expected: "On branch feature/tests-schema-validation", "nothing to commit, working tree clean".
- Run: git branch
  Expected: * feature/tests-schema-validation, and main.

At the end, report: the commit hash, current branch name, output of git log --oneline, output of git branch. Stop. Do not start Task 1.
```

---

## Prompt for Task 1 — Add dev dependencies

```
Context to load first:
- Read CLAUDE.md.
- Read docs/superpowers/plans/2026-04-21-tests-schema-validation.md, section "Task 1".

Your job: execute ONLY Task 1 (add dev dependencies). Do not touch other tasks.

Steps:
1. Create requirements-dev.txt with exactly the content specified in Step 1 of Task 1.
2. Install: pip install -r requirements-dev.txt
3. Verify pytest is installed: pytest --version (expect pytest 8.x.x).
4. Commit with the exact message from Step 3.

Verification:
- Paste the output of: pytest --version
- Paste the output of: git log --oneline -2

Stop after Task 1. Report files changed and command outputs.
```

---

## Prompt for Task 2 — Tests skeleton

```
Context to load first:
- Read CLAUDE.md.
- Read docs/superpowers/plans/2026-04-21-tests-schema-validation.md, section "Task 2".

Your job: execute ONLY Task 2 (tests skeleton).

Steps:
1. Create tests/__init__.py (empty).
2. Create tests/conftest.py with the exact content from Task 2, Step 2.
3. Verify pytest discovers the folder: pytest tests/ --collect-only
   Expected: "no tests ran" (the folder is empty but found without errors).
4. Commit with the exact message from Step 4.

Verification:
- Paste the output of: pytest tests/ --collect-only
- Paste the output of: ls tests/
- Paste the output of: git log --oneline -3

Stop after Task 2.
```

---

## Prompt for Task 3 — schemas.py: SplitResponse (TDD)

```
Context to load first:
- Read CLAUDE.md.
- Read docs/superpowers/specs/2026-04-21-tests-schema-validation-design.md, section 3.1.
- Read docs/superpowers/plans/2026-04-21-tests-schema-validation.md, section "Task 3".

Your job: execute ONLY Task 3. This is strict TDD:
1. Write the failing test FIRST (tests/test_schemas.py as specified in Step 1).
2. Run it, confirm the failure (Step 2). Paste the failure output.
3. Create schemas.py with exactly the code from Step 3 (SplitResponse model + _Base + imports). Do NOT add CharactersResponse, ScenePromptResponse, or DesignSpec — those are later tasks.
4. Run tests, confirm 5 pass (Step 4). Paste the passing output.
5. Commit with the exact message from Step 5.

Do not modify any other file. Do not add fields or validators beyond what the plan shows.

Report:
- The failing test output from Step 2.
- The passing test output from Step 4.
- Content of schemas.py after completion.
- Commit hash.

Stop after Task 3.
```

---

## Prompt for Task 4 — schemas.py: CharactersResponse

```
Context to load first:
- Read CLAUDE.md.
- Read docs/superpowers/specs/2026-04-21-tests-schema-validation-design.md, section 3.1.
- Read docs/superpowers/plans/2026-04-21-tests-schema-validation.md, section "Task 4".

Your job: execute ONLY Task 4. TDD:
1. Append the test class from Step 1 to tests/test_schemas.py (do not rewrite the file; append).
2. Run the new test class only, confirm ImportError (Step 2).
3. Append BootstrapCharacter + CharactersResponse to schemas.py (Step 3). Do not modify previously added models.
4. Run all schema tests, confirm 10 pass (Step 4).
5. Commit with the exact message from Step 5.

Do not anticipate later tasks (ScenePromptResponse, DesignSpec). Do not touch generate_comic.py.

Report:
- Test output from Step 2 (fail) and Step 4 (pass).
- Diff of tests/test_schemas.py and schemas.py (added lines only).
- Commit hash.

Stop after Task 4.
```

---

## Prompt for Task 5 — schemas.py: ScenePromptResponse

```
Context to load first:
- Read CLAUDE.md.
- Read docs/superpowers/specs/2026-04-21-tests-schema-validation-design.md, section 3.1 (specifically the ScenePromptResponse definition and validators).
- Read docs/superpowers/plans/2026-04-21-tests-schema-validation.md, section "Task 5".

Your job: execute ONLY Task 5. TDD:
1. Append the TestScenePromptResponse class and SCENE_OK fixture from Step 1 to tests/test_schemas.py.
2. Run the new class, confirm ImportError (Step 2).
3. Update the pydantic import line in schemas.py per Step 3 (add field_validator).
4. Append NewCharacter + ScenePromptResponse (with @field_validator methods) to schemas.py per Step 4. Use the exact code shown — do not rewrite without decorators.
5. Run all schema tests, confirm 20 pass (Step 5).
6. Commit with the exact message from Step 6.

Watch-outs:
- The pacing validator must reject any value outside {"slow", "normal", "fast"}.
- The subtitle_lines validator must reject any line with length > 42.
- model_config extra="allow" comes from the _Base class — do not add it again.

Report:
- Test output from Step 2 (fail) and Step 5 (pass).
- Diff of schemas.py (added lines).
- Commit hash.

Stop after Task 5.
```

---

## Prompt for Task 6 — schemas.py: DesignSpec

```
Context to load first:
- Read CLAUDE.md.
- Read docs/superpowers/specs/2026-04-21-tests-schema-validation-design.md, section 3.1 (DesignSpec).
- Read docs/superpowers/plans/2026-04-21-tests-schema-validation.md, section "Task 6".

Your job: execute ONLY Task 6. TDD:
1. Append the TestDesignSpec class and DESIGN_OK fixture from Step 1 to tests/test_schemas.py.
2. Run the new class, confirm ImportError (Step 2).
3. Append the DesignSpec model from Step 3 to schemas.py.
4. Run all schema tests, confirm 30 pass (Step 4).
5. Commit with the exact message from Step 5.

Do not touch generate_comic.py. Do not start wiring tasks (Task 12+).

Report:
- Test output from Step 2 (fail) and Step 4 (pass).
- Diff of schemas.py and tests/test_schemas.py (added lines).
- Commit hash.

Stop after Task 6.
```

---

## Prompt for Task 7 — test_pure.py: classify_error

```
Context to load first:
- Read CLAUDE.md.
- Read docs/superpowers/plans/2026-04-21-tests-schema-validation.md, section "Task 7".
- Read generate_comic.py lines 130-170 to see the actual classify_error implementation and RETRYABLE_STATUSES / FATAL_STATUSES constants.

Your job: execute ONLY Task 7. These are characterization tests — the function already works; the tests document its behavior.

Steps:
1. Create tests/test_pure.py with the content from Step 1. This is a new file; do not append to existing.
2. Run tests, confirm 14 pass (Step 2). Paste the output.
3. Commit with the exact message from Step 3.

Watch-out: the regex in classify_error extracts Retry-After from the error message text (not HTTP headers). Test messages must contain substrings like "retryDelay: 30" or a pattern matching `(\d+)s"?}` to produce a non-None retry_after.

Do not modify generate_comic.py. Do not start Task 8.

Report:
- Test output.
- Commit hash.
```

---

## Prompt for Task 8 — test_pure.py: backoff_delay

```
Context to load first:
- Read CLAUDE.md.
- Read docs/superpowers/plans/2026-04-21-tests-schema-validation.md, section "Task 8".
- Read generate_comic.py lines 172-183 (backoff_delay implementation).

Your job: execute ONLY Task 8.

Steps:
1. Append the TestBackoffDelay class from Step 1 to tests/test_pure.py.
2. Run the new class, confirm 6 pass (Step 2). Paste output.
3. Commit with the exact message from Step 3.

Watch-out: backoff_delay is randomized — tests use bounds and averages over many samples, not exact values. Do not change the seed; do not monkeypatch random.

Report:
- Test output.
- Commit hash.
```

---

## Prompt for Task 9 — test_pure.py: _fmt_srt_time

```
Context to load first:
- Read CLAUDE.md.
- Read docs/superpowers/plans/2026-04-21-tests-schema-validation.md, section "Task 9".
- Read generate_comic.py lines 748-755 (_fmt_srt_time).

Your job: execute ONLY Task 9.

Steps:
1. Append the TestFmtSrtTime class from Step 1 to tests/test_pure.py.
2. Run, confirm 8 pass (Step 2). Paste output.
3. Commit with the exact message from Step 3.

Report:
- Test output.
- Commit hash.
```

---

## Prompt for Task 10 — test_pure.py: estimate_duration

```
Context to load first:
- Read CLAUDE.md.
- Read docs/superpowers/plans/2026-04-21-tests-schema-validation.md, section "Task 10".
- Read generate_comic.py lines 738-747 (estimate_duration) and constants MIN_SCENE_DURATION, MAX_SCENE_DURATION.

Your job: execute ONLY Task 10.

Steps:
1. Append the TestEstimateDuration class from Step 1 to tests/test_pure.py.
2. Run, confirm 5 pass (Step 2). Paste output.
3. Commit with the exact message from Step 3.

Report:
- Test output.
- Commit hash.
```

---

## Prompt for Task 11 — test_pure.py: pick_scene_model + DOCUMENTATION SYNC

```
Context to load first:
- Read CLAUDE.md.
- Read docs/superpowers/plans/2026-04-21-tests-schema-validation.md, section "Task 11".
- Read generate_comic.py lines 261-270 (pick_scene_model) and constants COMPLEX_SCENE_CHAR_THRESHOLD, COMPLEX_SCENE_LENGTH_CHARS.
- Read TODO.md section 8 "Надёжность и тестирование".

Your job: execute Task 11 AND bundled documentation sync (pure-tests milestone is now complete — 5/5 functions covered).

Part A — Task 11 as written:
1. Append the TestPickSceneModel class from Step 1 to tests/test_pure.py.
2. Run, confirm 7 pass (Step 2).
3. Run the full suite: pytest tests/ -v. Expect 70+ tests pass total (Step 3).
4. Commit with the exact message from Step 4.

Part B — Documentation sync:
5. Update TODO.md section 8: replace
     "🔴 **Unit-тесты** для чистых функций: `classify_error`, `backoff_delay`, `_fmt_srt_time`, `estimate_duration`, `pick_scene_model`. Сейчас тестов нет вообще."
   with:
     "✅ **Unit-тесты** для чистых функций: `classify_error`, `backoff_delay`, `_fmt_srt_time`, `estimate_duration`, `pick_scene_model` — покрыты в `tests/test_pure.py` (апрель 2026)."
6. Update CLAUDE.md "Статус" section: under "🚧 В работе", add a sub-bullet under the subproject 1 entry:
     "  - ✅ Pure-функции покрыты тестами (task 11 плана)."
   Do not remove the subproject 1 block — schema validation is still in progress.
7. Stage CLAUDE.md and TODO.md. Commit with message:
     "docs: mark pure-function tests as done (TODO section 8)"

Verification:
- Run: pytest tests/ -v  (all green)
- Run: git log --oneline -15  (shows test commits + docs commit)
- Paste the diff of TODO.md and CLAUDE.md.

Report:
- Final pytest output.
- Commit hashes for both commits in this task.
- Diffs of TODO.md and CLAUDE.md.

Stop. Do not start Task 12.
```

---

## Prompt for Task 12 — Integrate schema param into call_llm_json

```
Context to load first:
- Read CLAUDE.md.
- Read docs/superpowers/specs/2026-04-21-tests-schema-validation-design.md, sections 3.2, 4, 5.
- Read docs/superpowers/plans/2026-04-21-tests-schema-validation.md, section "Task 12".
- Read generate_comic.py lines 26-50 (imports) and lines 185-258 (current call_llm_json).

Your job: execute ONLY Task 12.

Critical constraints:
- Preserve existing retry/fallback behavior exactly. The only additions are schema validation and re-prompt on ValidationError.
- base_prompt MUST be captured before the retry loop; current_prompt is what gets sent. On ValidationError, current_prompt = base_prompt + error_suffix. Do not accumulate suffixes across retries.
- Fallback recursion MUST pass schema=schema and base_prompt (not current_prompt). Otherwise the fallback inherits the error-suffixed prompt, corrupting the retry.
- Return .model_dump() on validation success so existing call-sites using data.get(...) keep working.

Steps:
1. Add imports per Step 1.
2. Replace the entire call_llm_json body per Step 2. Use the exact code shown in the plan.
3. Verify import works: python -c "import generate_comic"  (should print nothing, no errors).
4. Verify existing tests still pass: pytest tests/ -v
5. Commit with the exact message from Step 5.

Do NOT wire call-sites yet. Task 12 only changes the function signature and internals — call-sites get schema in tasks 13-17.

Report:
- Output of python -c "import generate_comic"
- pytest output.
- Diff of generate_comic.py (imports + call_llm_json only).
- Commit hash.

Stop after Task 12.
```

---

## Prompt for Task 13 — Wire split_story

```
Context to load first:
- Read CLAUDE.md.
- Read docs/superpowers/plans/2026-04-21-tests-schema-validation.md, section "Task 13".
- Read generate_comic.py lines 299-311 (split_story) to confirm the exact match target.

Your job: execute ONLY Task 13 — pass schema=SplitResponse to the single call_llm_json invocation inside split_story.

Steps:
1. Add schema=SplitResponse to the call as shown in Step 1. This is a minimal diff — one keyword argument added.
2. Verify: python -c "import generate_comic" && pytest tests/ -v  (all green).
3. Commit with the exact message from Step 3.

Do not modify any other function. Do not reformat the file.

Report:
- Diff of generate_comic.py.
- pytest output.
- Commit hash.

Stop after Task 13.
```

---

## Prompt for Task 14 — Wire bootstrap_characters

```
Context to load first:
- Read CLAUDE.md.
- Read docs/superpowers/plans/2026-04-21-tests-schema-validation.md, section "Task 14".
- Read generate_comic.py lines 608-642 (bootstrap_characters).

Your job: execute ONLY Task 14. Add schema=CharactersResponse to the call_llm_json invocation in bootstrap_characters.

Steps:
1. Apply the diff from Step 1.
2. Verify import + tests (Step 2).
3. Commit with the exact message from Step 3.

Report:
- Diff of generate_comic.py.
- pytest output.
- Commit hash.

Stop after Task 14.
```

---

## Prompt for Task 15 — Wire build_scene_prompt

```
Context to load first:
- Read CLAUDE.md.
- Read docs/superpowers/plans/2026-04-21-tests-schema-validation.md, section "Task 15".
- Read generate_comic.py lines 385-418 (build_scene_prompt). There are THREE call_llm_json invocations to touch.

Your job: execute ONLY Task 15. Add schema=ScenePromptResponse to all three call_llm_json invocations inside build_scene_prompt:
- The initial Flash call inside the try block.
- The Pro fallback call in the except block.
- The Pro re-run call triggered by COMPLEX_SCENE_CHAR_THRESHOLD.

Steps:
1. Apply both replacement blocks from Step 1. Double-check all three call_llm_json sites get schema=ScenePromptResponse.
2. Verify import + tests (Step 2).
3. Commit with the exact message from Step 3.

Watch-out: it is easy to miss the third invocation (the Pro re-run on many-characters). Grep the function after editing: `grep -n "call_llm_json" generate_comic.py` — every call inside build_scene_prompt should have schema=.

Report:
- Diff of generate_comic.py.
- Output of: grep -n "call_llm_json" generate_comic.py  (to verify all sites have schema=).
- pytest output.
- Commit hash.

Stop after Task 15.
```

---

## Prompt for Task 16 — Wire generate_design_spec

```
Context to load first:
- Read CLAUDE.md.
- Read docs/superpowers/plans/2026-04-21-tests-schema-validation.md, section "Task 16".
- Read generate_comic.py lines 717-731 (generate_design_spec).

Your job: execute ONLY Task 16. Add schema=DesignSpec to the call_llm_json invocation.

Steps:
1. Apply the diff from Step 1.
2. Verify import + tests (Step 2).
3. Commit with the exact message from Step 3.

Report:
- Diff of generate_comic.py.
- pytest output.
- Commit hash.

Stop after Task 16.
```

---

## Prompt for Task 17 — Wire batch path (in-place validation)

```
Context to load first:
- Read CLAUDE.md.
- Read docs/superpowers/specs/2026-04-21-tests-schema-validation-design.md, section 3.4.
- Read docs/superpowers/plans/2026-04-21-tests-schema-validation.md, section "Task 17".
- Read generate_comic.py lines 483-520 (batch_collect_scene_prompts) to understand the current results-loop structure.

Your job: execute ONLY Task 17. Wrap the batch response parsing with pydantic validation; on ValidationError, mark the scene as error in the results dict.

Critical constraints:
- The batch API is stateless — re-prompt is impossible here. Schema failure just marks the scene as error; --resume in realtime mode (through call_llm_json) later processes it with the re-prompt loop.
- Do NOT raise on ValidationError; continue the loop.
- The error string pattern is "schema: {ve}" per the plan.

Steps:
1. Replace the results loop per Step 1. Use the exact code in the plan.
2. Verify: python -c "import generate_comic" && pytest tests/ -v
3. Commit with the exact message from Step 3.

Report:
- Diff of generate_comic.py.
- pytest output.
- Commit hash.

Stop after Task 17.
```

---

## Prompt for Task 18 — Smoke test + FINAL DOCUMENTATION SYNC

```
Context to load first:
- Read CLAUDE.md.
- Read docs/superpowers/plans/2026-04-21-tests-schema-validation.md, section "Task 18".
- Read TODO.md section 8, README.md.

Your job: final smoke test + bundled documentation sync. Subproject 1 (tests + schema validation) is now complete.

Part A — Smoke test:
1. Ensure .env contains GEMINI_API_KEY (ask the user if unsure; do not fabricate).
2. Run the dry-run pipeline:
     python generate_comic.py --story story.txt --bootstrap --batch --dry-run --limit 3
3. Expected: finishes without ValidationError. output/progress.json has 3 scenes. Paste the tail of the log.
4. Inspect outputs:
     cat output/progress.json | head -50
     cat output/design_spec.json
5. Run the full test suite one more time: pytest tests/ -v  (all green).

If the dry-run fails with ValidationError from real data, STOP and report — the schema is too strict and needs relaxing based on actual observed data (do not silently loosen it; get user approval).

Part B — Documentation sync:
6. Update TODO.md section 8: replace
     "🔴 **Schema validation** ответов LLM через `pydantic` или `jsonschema`. Сейчас — `data.get(...)` с дефолтами, если LLM выдаст кривой JSON — тихо потеряем поля."
   with:
     "✅ **Schema validation** ответов LLM через `pydantic` — все 4 LLM-вызова (split, bootstrap, scene prompts, design spec) валидируются, retry-on-ValidationError встроен в `call_llm_json`. Batch path помечает сцену `status=error` при fail. Реализовано апрель 2026."

7. Update CLAUDE.md "Статус" section:
   - Move subproject 1 from "🚧 В работе" to "✅ Готово". Entry text:
       "- **Unit-тесты** для 5 чистых функций (`tests/test_pure.py`)."
       "- **Schema validation** 4 LLM-ответов через pydantic (`schemas.py`), retry-on-fail встроен в `call_llm_json`."
   - In the "Главные функции" table, update the call_llm_json row description to mention the new schema parameter.
   - In the "Правила и конвенции → LLM-интеграция" section, delete the note "После подпроекта 1:" — it is now the permanent rule.
   - In the "Roadmap" section, move item 1 below the completed list and renumber the roadmap so TTS becomes item 1.

8. Update README.md: append a new section after "Устойчивость к сбоям":
     ```
     ## Тесты

     ```bash
     pip install -r requirements-dev.txt
     pytest tests/ -v
     ```

     Покрыто: 5 чистых функций (`classify_error`, `backoff_delay`, `_fmt_srt_time`, `estimate_duration`, `pick_scene_model`) и pydantic-схемы для 4 LLM-ответов. Validation-fail вызывает re-prompt LLM с текстом ошибки.
     ```

9. Stage and commit the three doc files on the feature branch with message:
     "docs: mark subproject 1 (tests + schema validation) complete"

Part C — Merge feature branch to main:
10. Confirm you are on feature/tests-schema-validation and working tree is clean: git status
11. Switch to main: git checkout main
12. Merge the feature branch with a merge commit (not fast-forward, to preserve the subproject boundary in history):
      git merge --no-ff feature/tests-schema-validation -m "Merge subproject 1: unit tests + LLM schema validation"
13. Do NOT delete the feature branch — keep it as historical marker. Do NOT push anywhere (no remote configured).
14. Run final validation on main: pytest tests/ -v

Verification:
- Paste: git log --oneline --graph -25  (shows the merge commit + all task commits on the feature branch).
- Paste: git branch  (expect main current, feature/tests-schema-validation still present).
- Paste: git status  (clean tree).
- Paste: pytest tests/ -v  (final green run on main).
- Paste: diff of TODO.md, CLAUDE.md, README.md against the previous main commit (use: git show HEAD^ -- TODO.md or git diff HEAD^ HEAD -- TODO.md CLAUDE.md README.md).

Final report:
- Smoke test summary (did dry-run pass? any ValidationError encountered?).
- Test count in final pytest run.
- All commit hashes from tasks 0-18 in order (on feature branch), plus the merge commit hash on main.
- Confirmation that main now passes pytest.
- Anything unexpected or deviations from the plan.
```

---

## Execution notes

**Order:** strictly 0 → 1 → 2 → ... → 18. Each prompt assumes prior tasks are complete and committed.

**Between tasks:** review the agent's report (test output, diffs, commit hash). If anything deviated from the plan, fix before starting the next prompt.

**If the agent gets stuck:** do not let it invent workarounds. Stop, read the plan, adjust the prompt, rerun.

**Recovery:** if a task fails midway, `git reset --hard HEAD` (if no commit was made) or `git reset --hard HEAD~1` (if a bad commit was made). Then rerun the prompt.

**Why docs are bundled into 11 and 18:**
- Task 11 = pure tests milestone. TODO line 🔴 "Unit-тесты" is fully resolved at that point.
- Task 18 = schema validation milestone + subproject done. TODO line 🔴 "Schema validation" is fully resolved; CLAUDE.md Status section moves subproject 1 to "Готово"; README gains a Tests section.
- Intermediate tasks (git init, deps, individual schemas, individual pure-function tests, individual call-site wiring) do not complete any user-visible TODO item on their own; documenting them would churn the doc files without signal.

**Caveman mode for the agent user (you):** your replies to Gemini can stay terse if you want. The prompts themselves are in English so Gemini reads them naturally.
