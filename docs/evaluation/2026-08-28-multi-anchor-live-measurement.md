# KIS multi-anchor live measurement — dress25 KIS-only

**Thời điểm chạy:** 27/08/2026 (Asia/Saigon)  
**Phạm vi:** đúng 19 query KIS trong `dress25`; không chạy 5 QA, không chạy
TRAKE, không dùng `batch1_holdout13`.  
**Mục đích:** diagnostic sau P0 fix; GT dress25 là legacy/unverified nên kết quả
này **không phải promotion evidence**.

## Freeze trước khi chạy

| Trường | Giá trị |
|---|---|
| HEAD | `38f6d45dfaad9e62a1c2d1e24f627e9bbd537461` |
| P0 repair | `38f6d45` — bỏ `maxItems` không được Anthropic hỗ trợ |
| Runtime fingerprint | `19b507d658b9a838a321f0100dd1024866a47071c4dd20756a41442b76872c9e` |
| `LLM_BACKEND` | `api` |
| `LLM_API_MODEL` | `claude-sonnet-5` |
| `LLM_NO_CACHE` | unset — giữ semantics của evaluator 27/08 |
| Config snapshot digest | `983202bb5421909230a454a9c7fabd77219eeb2460ccc5aea64306020bab0428` |
| Scorer source digest | `12846d61f4bdd19b5a26313d0a505488dbf38437e010db792fc952f3b19b2c8f` |
| KIS query-set identity | `4163d5d92de509af737b8e733c67afcc04b03dc369bfd40bfff170d5d1a6e8d7` |
| Query source SHA-256 | `8495c58182380aff65c1c5fd6678ff5ae4196ad5d33fd2f460dedc8bbeda5edf` |
| GT source SHA-256 | `761b4ca139f3a21fbeb2826abcef8cb18988dfdbbf2886c71c147c72c0d6c7bd` |

Snapshot đầy đủ, gồm nội dung tất cả file `data/config/*.py`, nằm tại
`dev_set/results/run_20260827_kis19_multi_anchor_01/config_snapshot.json`.
Harness ghi snapshot trước khi kết nối DB/gọi provider, pin fingerprint cho mọi
query, checkpoint + fsync từng query và kiểm lại query/GT/runtime hash sau run.

Evaluator chính không có cờ lọc `task_type`, còn `--manifest` chỉ nhận hai
frozen set chính thức. Vì `dev_set/queries/dress25_kis.jsonl` vốn đã chứa đúng
19 KIS, harness diagnostic đọc trực tiếp file này, gọi production
`backend.tasks.runner.solve_query(total=100)` và chấm bằng chính
`dev_set.tools.scoring.recall_at_k()` / `final_score()` như evaluator dress25.
Không query, GT, frozen manifest, scorer hay config nguồn nào bị sửa.

## Execution integrity

| Kiểm tra | Kết quả |
|---|---:|
| `strategy=multi` | **19/19** |
| `strategy=single` | **0/19** |
| Fallback histogram | `None: 19` |
| `planner_error` | **0/19** |
| Anchor count | 2 anchors: 5 query; 3 anchors: 14 query |
| CLIP token guard | 46 token tối đa; **mọi anchor ≤ 60** |
| Output rows | 100/query; 0 violation |
| Frame mapping/bounds | 0 violation |
| Crash | **0** |

P0 fix đạt mục tiêu kỹ thuật: multi-anchor thực sự chạy cho toàn bộ 19 query,
không còn silent fallback và không crash.

## Aggregate diagnostic KIS

| Evidence | Final | R@1 | R@5 | R@20 | R@50 | R@100 |
|---|---:|---:|---:|---:|---:|---:|
| Baseline 21/08 (`0c4bf04`) | 0.4211 | 0.1053 | 0.4211 | 0.4211 | 0.5263 | 0.6316 |
| Pre-fix RUN 3 27/08 — single fallback | 0.4000 | 0.0526 | 0.4211 | 0.4211 | 0.5263 | 0.5789 |
| **Post-fix multi-anchor** | **0.3263** | **0.1053** | **0.2632** | **0.3158** | **0.4211** | **0.5263** |
| Post − baseline | **−0.0947** | 0.0000 | −0.1579 | −0.1053 | −0.1053 | −0.1053 |
| Post − pre-fix RUN 3 | **−0.0737** | +0.0526 | −0.1579 | −0.1053 | −0.1053 | −0.0526 |

R@1 phục hồi lên mức baseline, nhưng recall ở mọi cutoff còn lại đều giảm.
Final giảm 0.0737 so với single-fallback RUN 3 và giảm 0.0947 so với baseline.
Theo query: 4 tăng, 5 giảm, 10 đứng yên so với RUN 3; tổng score giảm 1.4 trên
19 query. Đây là degradation vật chất và cũng thấp hơn gate P0 đã đóng băng là
KIS Final 0.4000.

## Latency

| Metric | Seconds |
|---|---:|
| Median | 10.485 |
| P95, inclusive interpolation | 15.958 |
| Max | 35.402 |

Max thuộc query đầu/cold start. Latency steady-state nhìn chung dưới 14 giây và
không phải lý do tắt chính; quyết định bị chi phối bởi quality regression.

## Query-level diff

`delta` dưới đây là post-fix trừ pre-fix RUN 3. `failure_class` mô tả vì sao
query chưa đạt 1.0, không phải process crash.

| query_id | pre_fix_score | post_fix_score | delta | strategy | fallback_reason | anchor_count | CLIP tokens | latency | failure_class |
|---|---:|---:|---:|---|---|---:|---|---:|---|
| DRESS_KIS_01 | 0.8 | 1.0 | +0.2 | multi | None | 3 | 15, 12, 46 | 35.402s | None |
| DRESS_KIS_02 | 1.0 | 0.8 | −0.2 | multi | None | 3 | 17, 39, 24 | 11.071s | wrong_frame |
| DRESS_KIS_03 | 0.0 | 0.0 | 0.0 | multi | None | 3 | 20, 12, 18 | 9.568s | wrong_frame |
| DRESS_KIS_04 | 0.0 | 0.0 | 0.0 | multi | None | 3 | 9, 23, 19 | 8.956s | wrong_frame |
| DRESS_KIS_05 | 0.8 | 1.0 | +0.2 | multi | None | 3 | 34, 20, 38 | 8.962s | None |
| DRESS_KIS_06 | 0.0 | 0.0 | 0.0 | multi | None | 3 | 18, 11, 14 | 9.476s | retrieval_miss |
| DRESS_KIS_07 | 0.0 | 0.0 | 0.0 | multi | None | 2 | 21, 9 | 9.064s | wrong_frame |
| DRESS_KIS_08 | 0.8 | 0.0 | −0.8 | multi | None | 3 | 17, 22, 15 | 10.838s | wrong_frame |
| DRESS_KIS_09 | 0.4 | 0.4 | 0.0 | multi | None | 3 | 24, 23, 17 | 12.546s | wrong_frame |
| DRESS_KIS_10 | 0.8 | 0.2 | −0.6 | multi | None | 3 | 18, 9, 10 | 11.041s | wrong_frame |
| DRESS_KIS_11 | 0.0 | 0.0 | 0.0 | multi | None | 3 | 16, 14, 13 | 10.485s | wrong_frame |
| DRESS_KIS_12 | 0.2 | 0.8 | +0.6 | multi | None | 2 | 27, 18 | 9.157s | wrong_frame |
| DRESS_KIS_13 | 0.0 | 0.0 | 0.0 | multi | None | 2 | 17, 21 | 7.385s | wrong_frame |
| DRESS_KIS_14 | 0.0 | 0.0 | 0.0 | multi | None | 3 | 17, 18, 10 | 12.478s | retrieval_miss |
| DRESS_KIS_15 | 0.8 | 0.4 | −0.4 | multi | None | 3 | 14, 9, 15 | 11.544s | wrong_frame |
| DRESS_KIS_16 | 0.0 | 0.0 | 0.0 | multi | None | 3 | 26, 17, 27 | 13.798s | retrieval_miss |
| DRESS_KIS_17 | 0.8 | 0.8 | 0.0 | multi | None | 3 | 20, 17, 28 | 11.804s | wrong_frame |
| DRESS_KIS_18 | 0.8 | 0.2 | −0.6 | multi | None | 2 | 30, 15 | 8.480s | wrong_frame |
| DRESS_KIS_19 | 0.4 | 0.6 | +0.2 | multi | None | 2 | 26, 10 | 9.171s | wrong_frame |

## Decision

Multi-anchor executes reliably and its latency is mostly operationally
acceptable, but it materially degrades diagnostic KIS quality. Under the
deadline rule, do not tune weights/anchors/temporal behavior now. Use the safer
single-anchor path for Round 2 and defer any multi-anchor tuning until a later,
separately controlled experiment.

DISABLE MULTI-ANCHOR FOR ROUND 2
