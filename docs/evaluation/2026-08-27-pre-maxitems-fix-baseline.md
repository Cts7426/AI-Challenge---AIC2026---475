# Pre-repair evidence freeze — before `maxItems` fix

**Frozen:** 27/08/2026, before changing `ANCHOR_SCHEMA`.  This record preserves
the measured baseline and the two existing pre-repair evaluator runs.  It is
diagnostic evidence only; it is not a promotion decision and must not be
recomputed with another paid LLM evaluation.

## Scope and provenance

Primary sources read for this freeze:

- `reports/audit_context_20260827/00_MASTER.md`
- `reports/audit_context_20260827/10_eval_20260827_results.md`
- `reports/audit_context_20260827/eval_20260827/run1_scores.json`
- `reports/audit_context_20260827/eval_20260827/run3_scores.json`
- `reports/audit_context_20260827/06_baseline_dress25_scores_20260821.json`
- `reports/audit_context_20260827/04_pytest_full.txt`
- `docs/design/2026-08-27-round2-p0-design-freeze.md`
- `docs/plans/2026-08-27-round2-gap-triage.md`

All three rows below use the `dress25` split (19 KIS, 5 QA, 1 TRAKE).  Overall
is the average over its 25 query scores; KIS and QA are the corresponding
per-task averages.  `failure_class` from the evaluator means why a query did
not receive a perfect score, not necessarily a process crash.  The count below
therefore distinguishes explicit crashes from `status=failed`.

| Evidence | Commit | Runtime fingerprint | Overall | KIS | KIS R@1 | QA | TRAKE | Crashes / status failures |
|---|---|---|---:|---:|---:|---:|---:|---|
| Baseline reference — `20260821_0021` | `0c4bf04` | Not recorded in this legacy score artifact; do not infer one | 0.3520 | 0.4211 | 0.1053 | 0.1200 | 0.2000 | No `F0_CRASH` recorded; legacy artifact has no `status`, so status-failure count is unavailable |
| Current pre-repair RUN 1 — `20260827_153845_27d970c1` | `b419f6e` | `f9b986361ce69683e9c0b013858baba6d87d127d707f8f2c44e0461a6f2119db` | 0.3040 | 0.4000 | 0.0526 | 0.0000 | 0.0000 | 0 crashes / 5 failed (all QA) |
| Current pre-repair RUN 3 — `20260827_154710_27d970c1` | `b419f6e` | `f9b986361ce69683e9c0b013858baba6d87d127d707f8f2c44e0461a6f2119db` | 0.3627 | 0.4000 | 0.0526 | 0.2000 | 0.4667 | 0 crashes / 1 failed (`DRESS_QA_04`) |

Both current runs have the same query-set hash, GT-set hash, scorer source,
runtime fingerprint, and `promotion_ready: false`; neither has a verified
query ID.  RUN 2 (`20260827_154331_27d970c1`) was aborted with empty output and
is not a score row.

## KIS: multi-anchor was not measured

For **each** current pre-repair run, the captured KIS `query_plan` distribution
is:

| Observation | Count |
|---|---:|
| `_needs_multiple = True` | 19/19 |
| `strategy = multi` | 0/19 |
| `strategy = single` | 19/19 |
| `fallback_reason = planner_error` | 19/19 |

The provider rejected `ANCHOR_SCHEMA` because its array uses `maxItems`; the
error was caught and converted to the single-anchor fallback.  The Python
validator still independently caps anchors at three, so removing that schema
keyword is the narrowly frozen P0 repair.

> **THE CURRENT DRESS25 RESULT IS NOT A MEASUREMENT OF MULTI-ANCHOR PERFORMANCE.**

The current KIS values are measurements of the single-anchor fallback path.
They cannot establish either a gain or a regression for multi-anchor retrieval.

## Q&A runtime observed in RUN 3

`timings.total_seconds` for the five Q&A queries in RUN 3 was:

| Query | Seconds |
|---|---:|
| `DRESS_QA_01` | 195.9 |
| `DRESS_QA_02` | 210.6 |
| `DRESS_QA_03` | 360.6 |
| `DRESS_QA_04` | 404.2 |
| `DRESS_QA_05` | 476.2 |

Observed distribution: **min 195.9s, median 360.6s, mean 329.5s, max 476.2s**
(about 3.3–7.9 minutes/query).  RUN 3 produced CSV for 4/5 QA queries; the
remaining query was the one with `status=failed` / `missing_evidence`.  This is
an observed operational-risk distribution, not a controlled latency benchmark.

## Promotion status and interpretation boundary

- `batch1_holdout13` is contaminated by pre-PLAN tuning.
- Its GT is not human-verified.
- `0.82 / 0.82 / 0.75` are release thresholds in configuration, **not observed
  results**.
- Promotion remains invalid: the current evaluator artifacts record
  `promotion_ready: false` and no verified query IDs.
- `dress25` is diagnostic evidence, not promotion evidence.

Consequently, neither apparent RUN 3 improvement over baseline (`+0.0107`) nor
the RUN 1 decrease (`-0.0480`) can be promoted.  RUN 1 and RUN 3 also differ
despite sharing code, fingerprint, query set, and GT; this further prevents a
before/after conclusion without controlled replay evidence.

## Cheap verification performed at freeze time

- Current HEAD: `8cad8e2239e2a452348082438f3188f4a8553e05`
  (`docs: them goi context audit + ket qua do that 27/08`).  The score runs
  themselves remain tied to `b419f6e` above.
- Before adding this file, `git status --short` had no tracked modifications;
  it contained only the pre-existing untracked draft GT, three evaluator run
  directories, the P0 design freeze, and the gap-triage document.
- The archived 813-pass artifact did not identify its commit.  Because it was
  not demonstrably from current HEAD, full pytest was run without bytecode or
  pytest-cache writes, using an isolated temporary directory:

  ```powershell
  .\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider --basetemp C:\dev\aic2026\.pytest-tmp-pre-repair-freeze
  ```

  Result: **813 passed, 1 skipped, 2 warnings in 49.82s**.  The temporary
  directory created for this check was removed afterward.  An initial attempt
  without `--basetemp` was invalidated by sandbox denial of the user Temp
  directory; it was not a source-test failure.
- `docker compose ps` could not connect to the local Docker daemon
  (`permission denied` for `//./pipe/docker_engine`), so services were not
  currently available/expected for a meaningful preflight.  Development and
  release preflight were intentionally not run.

No paid LLM evaluation, holdout evaluation, or LLM call was made to reproduce
this evidence.  No production code was modified.

## Stop point

This is the pre-repair evidence freeze.  Do not consume another holdout run.
The next action, if authorized separately, is only the minimal P0 repair and
its fresh post-repair measurement with a clean runtime fingerprint.
