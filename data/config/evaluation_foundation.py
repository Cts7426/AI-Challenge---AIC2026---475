"""Protocol E01 tách khỏi retrieval; thay đổi schema/split phải tạo dataset version mới."""

SCHEMA_VERSION = "e01.annotation.v1"
DATASET_VERSION = "e01-v1"
SPLIT_TARGETS = {"validation": {"KIS": 12, "QA": 6, "TRAKE": 4},
                 "sealed_heldout": {"KIS": 12, "QA": 6, "TRAKE": 4}}
SAMPLING_SEED = "PP-E01-20260912-source-only-v1"
WORDING_JACCARD_THRESHOLD = 0.8
QA_NORMALIZATION_POLICY = "e01.qa.nfc_casefold_whitespace_v1"
QA_SEMANTIC_POLICY = "human_registered_variants_only_no_online_judge_v1"
DATASET_ROOT = "reports/post_preliminary_e01_20260912/dataset_v1"
FRAME_MAP_PATH = "data/derived/frame_map.parquet"
