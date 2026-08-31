# Final Round-2 KIS configuration check — dress25 KIS-only

**Thời điểm chạy:** 28/08/2026 (Asia/Saigon)  
**Phạm vi:** đúng 19 query KIS trong `dress25`; không chạy QA, TRAKE hay
`batch1_holdout13`.  
**Mục đích:** xác nhận đường vận hành single-anchor sau rollback Round 2. GT
`dress25` là legacy/unverified nên đây chỉ là **diagnostic**, không phải
promotion evidence.

## Freeze trước khi chạy

| Trường | Giá trị |
|---|---|
| HEAD | `d3eb66d7cf5c395ce6c607d3d078e5d6c73873f0` |
| Runtime fingerprint | `29bd614623abbe72f11dcc253fc23a81f46e01a6ea3085613fb9c5c5b75ea75e` |
| `LLM_BACKEND` | `api` |
| `LLM_API_MODEL` | `claude-sonnet-5` |
| `LLM_NO_CACHE` | unset |
| Feature gate | `data/config/multi_anchor.py::ENABLED = False` |
| Config snapshot digest | `12371e6bbe9c3fb85bbe66b0ed3cc1c5b4be7009a87521df47ce006a0f906ebf` |
| Scorer source digest | `12846d61f4bdd19b5a26313d0a505488dbf38437e010db792fc952f3b19b2c8f` |
| Scorer file SHA-256 | `632fb1983631cb77d03cdf4b99d638a2508c87140ec10d9580d79d64a89b170a` |
| Query-set identity | 19 ID `DRESS_KIS_01`…`DRESS_KIS_19`; `4163d5d92de509af737b8e733c67afcc04b03dc369bfd40bfff170d5d1a6e8d7` |
| Query source SHA-256 | `8495c58182380aff65c1c5fd6678ff5ae4196ad5d33fd2f460dedc8bbeda5edf` |
| GT source SHA-256 | `761b4ca139f3a21fbeb2826abcef8cb18988dfdbbf2886c71c147c72c0d6c7bd` |

Snapshot đầy đủ: `dev_set/results/run_20260828_round2_single_anchor_final_01/config_snapshot.json`.
Harness dùng cùng `solve_query(total=100)`, `recall_at_k()` và `final_score()`
như phép đo KIS ngày 27/08; không sửa source query, GT, scorer, mã production
hay config.

## Execution integrity

Trong process đo, `backend.retrieval.multi_anchor.llm()` và
`search_multi()` được bọc fail-closed: bất kỳ lần gọi nào sẽ dừng run với
`ROLLBACK_INVALID`. Cả hai bộ đếm đều bằng 0 sau run.

| Kiểm tra | Kết quả |
|---|---:|
| `strategy=single` | **19/19** |
| `strategy=multi` | **0/19** |
| Multi-anchor planner `llm()` calls | **0** |
| `search_multi()` calls | **0** |
| `fallback_reason=None` | 19/19 |
| Anchor count | 1 anchor: 19/19 |
| CLIP token | N/A cho single-anchor plan; không có expanded anchor để encode |
| Output rows | 100/query; 0 violation |
| Crash | **0** |
| Frame mapping/bounds violations | **0** |
| Planner error | **0** |

Rollback vì vậy hợp lệ: production thực thi đúng single-anchor path và không
còn lời gọi multi-anchor im lặng.

## Aggregate diagnostic KIS

| Evidence | Final | R@1 | R@5 | R@20 | R@50 | R@100 |
|---|---:|---:|---:|---:|---:|---:|
| Baseline 21/08 | 0.4211 | 0.1053 | 0.4211 | 0.4211 | 0.5263 | 0.6316 |
| Pre-fix RUN 3 — single fallback | 0.4000 | 0.0526 | 0.4211 | 0.4211 | 0.5263 | 0.5789 |
| Multi-anchor measurement | 0.3263 | 0.1053 | 0.2632 | 0.3158 | 0.4211 | 0.5263 |
| **Final Round-2 single-anchor check** | **0.4000** | **0.0526** | **0.4211** | **0.4211** | **0.5263** | **0.5789** |

So với pre-fix RUN 3, Final và R@1 khớp đúng ở lần đo này. So với baseline
21/08, Final thấp hơn 0.0211 và R@1 thấp hơn 0.0526. So với phép đo
multi-anchor, Final cao hơn 0.0737; R@5/R@20/R@50/R@100 lần lượt cao hơn
0.1579/0.1053/0.1053/0.0526. Chênh lệch runtime retrieval/LLM có thể tồn tại,
nhưng không có dấu hiệu hồi quy do thao tác disable.

## Latency và failure class

| Metric | Seconds |
|---|---:|
| Median | 0.558 |
| P95, inclusive interpolation | 2.668 |
| Max | 11.762 |

`failure_class`: `None` 1, `wrong_frame` 14, `retrieval_miss` 4. Không có
crash hay lỗi mapping. Độ trễ operational chấp nhận được; max là cold-start
của `DRESS_KIS_01`.

## Query-level diagnostic scores

| query_id | Final | R@1 | R@5 | R@20 | R@50 | R@100 | latency | failure_class |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| DRESS_KIS_01 | 0.8 | 0.0 | 1.0 | 1.0 | 1.0 | 1.0 | 11.762s | wrong_frame |
| DRESS_KIS_02 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.281s | None |
| DRESS_KIS_03 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 1.006s | retrieval_miss |
| DRESS_KIS_04 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 1.008s | wrong_frame |
| DRESS_KIS_05 | 0.8 | 0.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.456s | wrong_frame |
| DRESS_KIS_06 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 1.658s | retrieval_miss |
| DRESS_KIS_07 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.809s | wrong_frame |
| DRESS_KIS_08 | 0.8 | 0.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.517s | wrong_frame |
| DRESS_KIS_09 | 0.4 | 0.0 | 0.0 | 0.0 | 1.0 | 1.0 | 0.558s | wrong_frame |
| DRESS_KIS_10 | 0.8 | 0.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.742s | wrong_frame |
| DRESS_KIS_11 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.541s | wrong_frame |
| DRESS_KIS_12 | 0.2 | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 | 0.514s | wrong_frame |
| DRESS_KIS_13 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.532s | wrong_frame |
| DRESS_KIS_14 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 1.133s | retrieval_miss |
| DRESS_KIS_15 | 0.8 | 0.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.544s | wrong_frame |
| DRESS_KIS_16 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.980s | retrieval_miss |
| DRESS_KIS_17 | 0.8 | 0.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.420s | wrong_frame |
| DRESS_KIS_18 | 0.8 | 0.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.367s | wrong_frame |
| DRESS_KIS_19 | 0.4 | 0.0 | 0.0 | 0.0 | 1.0 | 1.0 | 0.461s | wrong_frame |

## Decision

Mục tiêu rollback đạt: single-anchor thực thi cho toàn bộ 19 query, không có
planner/search multi-anchor, không crash, không vi phạm frame mapping và độ trễ
vận hành chấp nhận được. Không tune tham số nào sau phép đo.

KIS CONFIG READY FOR ROUND 2
