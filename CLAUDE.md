# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

agent-R tailors a YAML master resume to a job ad with OpenAI models. It is a learning project for LLM evals, so most of the code is evals of each pipeline step. MVP goal (PLAN.md): any resume (YAML) plus any job ad gives a complete, tailored resume where every line is true. The three promises are **Honest** (judge eval), **Relevant** (selection eval) and **Complete** (code checks). PLAN.md holds the backlog (items A–D) and the rules.

## Commands

There is no build, linter or test suite. Use the venv interpreter. `tracing.py` loads `.env`, which needs `OPENAI_API_KEY` and `PHOENIX_COLLECTOR_ENDPOINT` (must end in `/v1/traces`). Every script imports it, so a Phoenix endpoint must be set even when tracing is suppressed.

```bash
.venv/bin/python tailor.py master_resume.yaml jds/<jd>.txt   # full pipeline, prints the rendered resume
.venv/bin/python evals.py [cases.json] [--per-pair] [--guard] [--trace]   # judge eval → TP/FN/FP/TN
.venv/bin/python classify_eval.py [--test] [--trace]          # JD classifier accuracy on dev (default) or test split
.venv/bin/python relevance.py [--trace]                       # select() must-recall / never-picks per JD
.venv/bin/python summary_eval.py [resume.yaml] [--trace]      # prints describe()'s overview pick per job
```

- `evals.py` batches all pairs into one judge call by default. Use `--per-pair` to match how `tailor()` calls the judge. `--guard` only counts a flag when the judge's `added` quote really appears in the rewrite.
- The evals call the API with temperature 0, but gpt-4o is still not fully stable, so run each eval 2–3× before comparing results.
- Environment variables: `MODEL` (default gpt-4o-mini, used by generate/classify/describe), `PICKER_MODEL` (select, default gpt-4o), `JUDGE_MODEL` (check, default gpt-4o).

## Architecture

`tailor()` in `tailor.py` runs: `classify(jd)` → `select()` → `generate()` → per-bullet `check()` → revert → `render()`.

- **Prompts are module-level constants** in `tailor.py` (`GEN`, `CHECK`, `SELECT`, `CLASSIFY`, `OVERVIEW`). Every LLM call goes through `ask()`, which uses `client.responses.parse` with a Pydantic `text_format`.
- **Bullet IDs are enforced by the schema.** `Master` loads the YAML and builds dynamic Pydantic models (`create_model`) whose fields are `Literal[...]` of the valid bullet IDs and skill names, so the model cannot invent IDs or skills. `select` and `describe` build their own `Literal` schemas the same way.
- **Honesty guard:** `generate()` rewrites the selected bullets in the JD's terminology. `check()` judges each (source, rewrite) pair on its own. Any rewrite that fails is reverted to the original bullet text. The `added` field is only a debugging aid and is not reliable.
- **JD type drives layout:** `classify()` returns tech, non-tech or adjacent. For non-tech JDs, `select` leaves out project bullets and `render.py` leaves out the Projects section. `ORDER` in `render.py` sets the section order for each type.
- **render.py** sorts jobs and education by date, newest first ("Present" sorts first). It always shows every job. A job with no selected bullet gets its overview bullet from `summarize()`.
- **summarize()/describe()** pick ONE existing bullet ID per job as its overview. The pick does not depend on the JD. It is cached in `<resume>.summaries.json` and recomputed only when that job's title or bullets change.
- `tracing.py` sets up Phoenix/OpenInference tracing. Functions are decorated with `@tracer.chain()` / `@tracer.agent()`. The evals wrap calls in `suppress_tracing()` unless `--trace` is passed.

## Data (mostly gitignored)

- `master_resume.yaml`: the user's resume. Sections are `contact`, `experience`, `projects`, `education`, `skills` and `licences_clearances`, and each bullet has an `id` such as `exp_<job>_b<n>` or `proj_<x>_b<n>`. `*.yaml` is gitignored, so this file has no git history. Edit it with care.
- `render.py` and `Master` hard-code this YAML's fields, so a resume with a different schema will raise KeyError. Making the schema portable is deferred.
- `eval_set.json`: judge cases. Each case is self-contained, with `source`, `rewrite` and `label` (inflated or ok), and needs no resume file.
- `jd_types.json`: JD labels for the classifier, split into dev and test. `relevance_set.json`: must/never bullet labels per JD. These labels are stale (bullet IDs changed when the resume was rewritten) and need relabelling.
- `jds/`: the job ads. `out/`: past runs.

## Rules

- Gitignore any file that contains personal details (resume content, job history, contact data, run outputs or logs that quote bullets) as soon as it is created, before anything is committed. Check `git check-ignore -v <file>` for new data files.
- Code must be clean and DRY. Write the minimal code, with no boilerplate, no dead code and no duplicated logic; reuse existing helpers such as `ask()` and `Master`. Add a comment only when it is strictly necessary, meaning the code cannot make the why clear on its own. Explain everything else in chat.
- Make structural changes only. Never add one resume's words to a prompt.
- Tune on the dev split and only check on the test split.
- Make one change at a time, then run the relevant eval 2–3× and compare against the previous baseline.
