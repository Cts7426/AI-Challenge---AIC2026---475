# H02 source/change ledger

Base `235414784b5ee80b9552fd7fe7ce898db1cbf35b`, tree `55a354bcc82e603dbcb0806a0b757bac9658ab13`. 25 file source/test/tooling; H01 là ledger riêng15file.

| File | SHA-256 hiện tại |
|---|---|
| `backend/api/main.py` | `2fc664211207372e4141fb7522389b6a8054d1e0409f96c84bf9ee7217b24859` |
| `backend/common/qa_contract.py` | `8ef46aad643963bd02792bf0b242cfccc073b7b211e00f1a92dff3b2607d8fcb` |
| `backend/export/exporter.py` | `707d93aa84f955259af29280cce862fe2ee4ebd41570825a6934f79500c8b56c` |
| `backend/export/qa_variants.py` | `82537209d22cfc5ac1142b0c3bf2e834675ef10c17af587511face5e17dc4c25` |
| `backend/export/release_rehearsal.py` | `a8c123bba67094231eaec8d5cbde108796240d9849bea77f59a69c21e2f0dd59` |
| `backend/tasks/qa.py` | `dfbb5f379637a960f62d2dfc90435e94e731cfb33ffed1ec99fcb3df10b22b06` |
| `backend/tasks/qa_portfolio.py` | `083f9b9729737776c7631fafd5a70b671c4a3c3b2727aca8bed7bf10e5412ce8` |
| `backend/tasks/runner.py` | `7468bac058d48b68f289464a6049195ef724bbda242118e3d0cc63399d7dc78d` |
| `data/config/qa_hypotheses.py` | `397fed79a217807e8e556f87cdb3a78a8b27edd1ebfe89ebac8c974c0cc03e3a` |
| `data/config/submit_format.py` | `716631fd3b017706297e9327e1431b5e6c5f9abae332af1c181829d9e3184a02` |
| `dev_set/tests/test_frozen_evaluator_integration.py` | `9b1af1a0bd06670662a97e33f3f38e4426c28f213e8e64263899d2254beffb7a` |
| `dev_set/tools/promotion_gate.py` | `790b31562b0f75d39442a9eb7573592d58b307f5ff596f674449a522284ab70a` |
| `dev_set/tools/run_evaluation.py` | `4cf6acd0a369fec50fcf1acbdece4173528222af7960e77c663d32959b94958b` |
| `run.py` | `f35803d49bcb4d6dce017d22c45a2bc1aba83e615f0db2db2035295fae11d3be` |
| `run_minimal.py` | `e6965843cb6edc71d860a2da7c73e620ae34001ef94f85e6d20918241e3e0228` |
| `scripts/manual_qa_override.py` | `fa38a6ae0731a0076b098064a77d9f8e9e0813c4060526473990a7473e6b083b` |
| `scripts/preflight_check.py` | `2b6a4ea1307278cf0907cfc924f74ade6003b618892a848529eb22ff85cee3bd` |
| `scripts/run_reproducible_baseline.py` | `a3bf1ebd7d44a8f72cc1b7cb2dadde8ea147e2d4b024f5026c13a3e80f671cec` |
| `tests/test_api_search.py` | `e1b1024c076554e64397c32b56ce220740243e37009c78883195bc13ec988ba9` |
| `tests/test_h02_contract.py` | `8ef7cf2b77986f82d19a44c2bea300923a4a749d5292290a17ebc087338a793e` |
| `tests/test_manual_qa_override.py` | `c2e516ac97ec79ae2a86583c8572552e419e931f90130e78116010699f6ea0bf` |
| `tests/test_qa.py` | `17483eccecf157b07fa69123d5757a67e4d204cb84bb1888ac91a9aab5b981d7` |
| `tests/test_qa_hypotheses.py` | `ab72bd00f43636c8a41b67f324bf688009dbe11350d73e26d9f1cdec5f03d24f` |
| `tests/test_run.py` | `1a38c886664e28805f03ac3418ff9487a9a131d02e4781acb2d8f9c994beed35` |
| `tests/test_task_runner.py` | `07fb47cccb010ba29e1de6bd8b08ded75f69f99390f321bc805ee346e0574e2c` |

Patch bao gồm cả file mới; snapshot ZIP chỉ có source, không key/data/cache. Report tooling có hash trong JSON. Không gán toàn bộ mixed commit cho H02.
