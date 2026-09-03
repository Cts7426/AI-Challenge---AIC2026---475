# Audit context pack — 27/08/2026

**Đọc `00_MASTER.md` trước.** Nó trả lời đủ mục A–Z và trỏ tới từng file bằng chứng.

**Rồi đọc `10_eval_20260827_results.md`** — có số đo thật before/after và một
phát hiện P0: tính năng multi-anchor của Task 3 chưa từng thực thi ở production
(19/19 query `planner_error` do lỗi 400 bị nuốt im lặng).

## Gói context tối thiểu (10 mục) — ánh xạ

| # | Yêu cầu | File |
|---|---|---|
| 1 | `PLAN.md` | `docs/PLAN.md` |
| 2 | `docs/product-spec.md` | `docs/product-spec.md` |
| 3 | Audit Report | `audit_reports/` (16 file, bắt đầu từ `00_final-review.md`) |
| 4 | `git status --short` | `01_git_state.txt` |
| 5 | `git log --oneline -15` | `01_git_state.txt` |
| 6 | diff implementation | `03_implementation_b8090cd..HEAD.diff` (401 KB) + `03b_...diffstat.txt` |
| 7 | repository tree | `02_repo_tree.txt` |
| 8 | output test suite | `04_pytest_full.txt` |
| 9 | evaluation before/after | **`10_eval_20260827_results.md`** ⭐ + `06_baseline_dress25_scores_20260821.json` + `eval_20260827/` + `08_holdout13_history.txt` |
| 10 | holdout có bị dùng để tune không | `08_holdout13_history.txt` + `manifests/holdout_log.md` — **CÓ, Case 3**, xem `00_MASTER.md` §M |

## Toàn bộ file

```
00_MASTER.md                              ← trả lời A–Z
README.md                                 ← file này
01_git_state.txt                          branch / HEAD / status / log / baseline
02_repo_tree.txt                          cây thư mục (bỏ .git .venv data/raw cache)
03_implementation_b8090cd..HEAD.diff      diff đầy đủ 40 file, +7828/−337
03b_implementation_diffstat.txt           diffstat + name-status
04_pytest_full.txt                        813 passed, 1 skipped + số test mỗi file
05_promotion_gate_actual.json             gate chạy thật hôm nay → BLOCKED
06_baseline_dress25_scores_20260821.json  baseline duy nhất tái lập được (21/08)
07_runtime_env.txt                        Python/OS/RAM/package/service/.env redact
08_holdout13_history.txt                  lịch sử chấm điểm đúng 13 câu holdout
09_architecture_constants.txt             fusion order + mọi hằng số config
10_eval_20260827_results.md               ⭐ ĐO THẬT 27/08: before/after, root cause
                                             planner_error, nondeterminism, đính chính §Q
eval_20260827/                            scores.json + config_snapshot của run 1 & run 3

docs/          PLAN, product-spec, ARCHITECTURE, testing, deployment, contest
audit_reports/ final-review, integration-fix, ledger, task-1..5 brief/report/review
manifests/     batch1_holdout13.json, batch1_round1_queries.json,
               holdout_log.md, sotuyen1_p1_draft_gt.jsonl (bản nháp GT, status TODO)
```

## Không có trong gói (cố ý)

- API key / token / credential — `.env` đã redact trong `07_runtime_env.txt`
- raw dataset, video, keyframe, `.npy`, Milvus index dump, cache binary
- `dev_set/results/run_*/` đầy đủ — chỉ trích số liên quan vào `06_` và `08_`

## Hai mục đã xác nhận (27/08)

- **§Y priority:** `1. có số đo thật → 2. no crashes → 3. KIS → 4. Q&A →
  5. reproducibility → 6. architecture`.
- **§Z deadline:** còn **~1 ngày** — đợt 2 sơ tuyển tối **28/08 19:30**.
  Repo đang ở chế độ "dưới 24 giờ": chỉ sửa crash / format / mất dữ liệu /
  sai mapping / P0. Mốc tiếp theo 04/09.
