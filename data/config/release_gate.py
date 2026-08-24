"""Ngưỡng promotion/release được gom một chỗ để audit không lệch code."""

from __future__ import annotations


PROMOTION_GATE_SCHEMA_VERSION = 1
PROMOTION_SCORER_CONTRACT = "btc-final-score-v1"
PROMOTION_SCORER_POLICY = "semantic"

HOLDOUT_MANIFEST_ID = "batch1_holdout13"
HOLDOUT_EXPECTED_TASK_COUNTS = {"KIS": 10, "QA": 3}
HOLDOUT_EXPECTED_QUERY_IDS = (
    "KIS_001", "KIS_002", "KIS_003", "KIS_004", "KIS_005",
    "KIS_006", "KIS_007", "KIS_008", "KIS_009", "KIS_010",
    "QA_011", "QA_012", "QA_013",
)
HOLDOUT_QUERY_SET_SHA256 = (
    "faa40137c092a7039bcf307c0fa193e8b37a033cefcded32757a3018890ffa65"
)
HOLDOUT_OVERALL_MIN = 0.82
HOLDOUT_KIS_MIN = 0.82
HOLDOUT_QA_MIN = 0.75

REGRESSION_MANIFEST_ID = "batch1_round1_queries"
REGRESSION_EXPECTED_COUNT = 25
REGRESSION_EXPECTED_QUERY_IDS = (
    "query-p1-1-kis", "query-p1-10-kis", "query-p1-11-kis",
    "query-p1-12-kis", "query-p1-13-kis", "query-p1-14-kis",
    "query-p1-15-qa", "query-p1-16-trake", "query-p1-17-qa",
    "query-p1-18-kis", "query-p1-19-kis", "query-p1-2-kis",
    "query-p1-20-kis", "query-p1-21-kis", "query-p1-22-kis",
    "query-p1-23-kis", "query-p1-24-kis", "query-p1-25-kis",
    "query-p1-3-qa", "query-p1-4-kis", "query-p1-5-kis",
    "query-p1-6-kis", "query-p1-7-kis", "query-p1-8-kis",
    "query-p1-9-qa",
)
REGRESSION_QUERY_SET_SHA256 = (
    "9b6b85b336a41ef1218efda19f497647d324a4cc656ba86868ea4d6beb1cb0ea"
)
REGRESSION_SCORE_EPSILON = 1e-12

RELEASE_RECEIPT_SCHEMA_VERSION = 1
RELEASE_CONFIG_SNAPSHOT_SCHEMA_VERSION = 1
RELEASE_EVIDENCE_CACHE_MANIFEST_SCHEMA_VERSION = 1
