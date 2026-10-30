# Konwinski Prize winner, forum thread on model weakness, and the skill-script lever (30 Oct 2026)

## Inputs (pasted by the user)
- Konwinski Prize (Kaggle, 2024-25): SWE-bench-style issues collected after the deadline; any open model and any Python;
  30 minutes per issue; wrong patches penalised (score = (correct - wrong) / total), so skipping was rewarded.
- 1st place write-up (Eduardo Rocha de Andrade): Agentless 1.5 + Qwen2.5-Coder-32B. Private result 9 correct, 2 wrong,
  109 skipped of 120. Key parts: generate 5-10 reproduction tests with context from the repo's own tests (imports,
  class and function skeletons), keep only tests that reproduce the issue; hierarchical localization (files, then
  functions, then lines); 8 candidate patches in SEARCH/REPLACE format; keep patches that make a reproduction test pass and
  do not worsen the existing tests; global and per-issue time limits. "Agent mode" and reasoning models did not help.
- Forum (Gemma 4, Oct 2026): Yurnero (1st, 0.29) thinks 0.31 is reachable; says private gold patches are all verified.
  Sahil Das: Gemma 4 "behaves similarly no matter what the system prompt is and repeats the same errors", especially
  with writes. Adam Johnson: about 30% of the 129 public tasks on the Kaggle side.

## What transfers
- Our scoring has no penalty for wrong patches, so never skip; always leave an edit.
- We cannot run an Agentless Python pipeline: submissions are declarative YAML. But skills may ship `.py` scripts
  (HARNESS_README 2.2 and the allowed-extension list; tools `load_skill`, `load_skill_resource`, `run_skill_script`).
  A script costs no model tokens to write, so deterministic work (ranking candidate files, printing file outlines,
  applying a search/replace edit safely, running a targeted test and summarising the exit code) can move from the model
  into code. That matches both the Agentless lesson (small models do better in a fixed pipeline) and the forum
  observation that Gemma repeats the same mistakes whatever the prompt says.
- Unknowns to probe before building on it: where scripts run (task sandbox with /workspace access?), the exact
  `run_skill_script` arguments, whether stdout returns to the model, time cost per call.

## Proposed next experiments
1. x_skill_probe: one tiny skill whose script prints its working directory, `git status`, and lists /workspace.
   Run on 2 tasks in the runner notebook (about 15 minutes) to learn the mechanics.
2. v13_locate_skill: v12a + a `locate` skill (rank files by grep + BM25 on the issue's identifiers and words, print
   top 10 with class/function outlines and line numbers) and an `outline` script. Prompt: call locate first.
   Compare with v12a on about 40 valid tasks in the scorer-like sandbox.
