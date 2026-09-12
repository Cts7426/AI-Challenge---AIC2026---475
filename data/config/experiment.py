"""Phạm vi snapshot H01; chỉ thu identity, không đổi cấu hình retrieval."""

SOURCE_GLOBS = ("backend/**/*.py", "scripts/*.py", "run.py", "dev_set/tools/*.py")
CONFIG_GLOBS = ("data/config/*", "backend/requirements*.txt", "pytest.ini", "docker-compose*.yml")
DATA_GLOBS = ("data/manifests/**/*", "data/derived/*.parquet", "data/derived/*.meta.json",
              "data/derived/*.npy", "data/derived/*.json", "reports/BATCH1_OPERATIONAL_MANIFEST_20260821.json")
CACHE_DIRS = ("data/cache/llm", "data/cache/qa_hypotheses")
MODEL_GLOBS = (".cache/huggingface/hub/models--timm--vit_base_patch32_clip_224.openai/blobs/*",
               ".cache/clip/ViT-B-32.pt")
ES_INDEXES = ("metadata", "objects", "ocr", "asr")
# Chỉ whitelist knob/path công khai; không thu os.environ toàn bộ hoặc secret.
RUNTIME_ENV_KEYS = ("LLM_BACKEND", "LLM_API_MODEL", "LLM_GEMINI_MODEL", "LLM_LOCAL_MODEL",
                    "VECTOR_BACKEND", "QA_INFERENCE_MODE", "LLM_NO_CACHE", "LLM_CACHE_DIR",
                    "QA_HYPOTHESIS_CACHE_DIR", "KEYFRAMES_DIR", "DERIVED_KEYFRAMES_DIR",
                    "HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "OMP_NUM_THREADS",
                    "MKL_NUM_THREADS", "PYTHONHASHSEED")
