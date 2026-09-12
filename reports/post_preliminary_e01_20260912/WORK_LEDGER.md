# PP-E01 — work ledger

Authorization: [authorization.txt](authorization.txt). H02 correctness approved; H01 performance baseline not promoted. E01 dataset/protocol/instrumentation support only; H03 implementation and paid providers not authorized.

Starting HEAD `7842d11`; source H02 `4fe4f2e`. No production source WIP; H01 reports and context handoff are preserved outside E01. Source files/config/tests snapshot and hashes created before E01 code edits.

Work sequence:

1. Capture current read-only resource/runtime/scorer identity under external-dispatch hard guard.
2. Preserve consumed-set roles in a new registry version; prepare source-only sampling with declared leakage limits.
3. Version annotation schema and append-only human annotation/sealing tools; no system answers in initial packet.
4. Reserve validation/held-out split before any evaluation, 12/6/4 per split. Report unfilled/unverified honestly.
5. Test integrity, human provenance, leakage/sealing and consumption gates; full suite/selfcheck as applicable.
6. H03a design/metrics/baseline prerequisites and checkpoint A–O, then STOP.

Human verification is an expected required input, not an agent-generated label. No retrieval/evaluation is run on new dataset items during E01.

## Kết quả bàn giao

- Resource capture read-only hoàn tất, 177.321 asset hashes và toàn bộ ES/Milvus content digests; collector gaps rỗng; provider/dispatch 0.
- Registry mới 32 entries giữ nguyên role 18 entries cũ. Source-only sampling 44 video từ 726 eligible sau loại 147 metadata video đã dùng. Tạo 44 packets, 9.257 keyframes, chưa tạo query/GT.
- Dataset v1 revision 1 và split reservations 12/6/4 mỗi bên; schema/tool append-only/seal/consume/correction có tests. Draft manifest hashes lưu, không tạo seal thật.
- Leakage: 86 exact shared hash groups, 23 cặp qua split cần human review. MP4 local 0/44; video/dense evidence thiếu cho temporal claims.
- Focused 28 passed; full 1009 passed/1 skipped. Tự review sửa quality independence chỉ sau seal; selfcheck cuối xác nhận 1009 passed/1 skipped và preflight 20/0/2, exit 1 vì hai GT gaps cũ. Không sửa GT.
- Frozen source/config 213 file, H02 evidence 69 file, historical query/GT/manifest sources 36 file không đổi hash. Không sửa retrieval/model/slot weights.
- CHECKPOINT_E01 A–O và H03a preregistration đã lưu. **NOT READY FOR H03A** vì human GT/leakage/seal chưa có; dừng, không thực hiện H03.
