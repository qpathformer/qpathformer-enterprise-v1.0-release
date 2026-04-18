# Repository Structure — Q-Pathformer Enterprise v1.0

---

## Purpose

This document provides a **full structural map of the repository**.

It is intended for:

* reviewers inspecting the release
* developers navigating execution paths
* operators validating artifact completeness

This file reflects the **actual release tree at v1.0**.

---

## Root Structure

```text
C:\
├── docs/
├── path_1_tr_corpus_reference/
├── path_2_access_mode_canonical/
├── path_3_external_custom_adapter/
├── scripts/
└── shared/
```

---

## docs/

```text
docs/
├── architecture/
├── execution/
└── orientation/
    └── results_docs/
```

### Role

* documentation entry point
* execution guidance
* architecture reference
* release results

---

## path_1_tr_corpus_reference/

```text
path_1_tr_corpus_reference/
├── 01_source/
│   ├── corpus_snapshot/
│   ├── readme_refs/
│   └── tr_docs/
│       └── access_mode/
├── 02_signals/
├── 03_dataset/
│   └── checkpoint_v4_strict/
├── 04_state1_package/
│   └── QPDS-TR-STRICT-ID3-001/
│       └── freeze/
├── 05_runs/
│   └── FTRUN-.../
│       ├── checkpoints/
│       └── model/
├── 06_review/
└── 07_logs/
    └── run_logs/
```

### Role

* deterministic TR corpus processing
* signal extraction → dataset → STATE_1 package
* controlled LoRA validation runs
* no runtime model dependency

---

## path_2_access_mode_canonical/

```text
path_2_access_mode_canonical/
├── 01_source/
│   └── ID_3 freeze packages
├── 02_signals/
│   ├── runtime_generated/
│   └── source_bridge/
├── 03_dataset/
│   ├── candidates/
│   └── training_packages/
├── 04_state1_package/
├── 05_runs/
│   └── FTRUN-.../
│       ├── checkpoints/
│       └── model/
├── 06_review/
└── 07_logs/
    └── run_logs/
```

### Role

* canonical `ID_2 → ID_3` lifecycle execution
* runtime signal generation and routing
* candidate formation, promotion, and freeze
* primary CSC evidence generation pathway

### Notes

* runtime signals generated under `02_signals/runtime_generated/`
* source artifacts bridged under `source_bridge/`
* promotion requires grouped candidates

---

## path_3_external_custom_adapter/

```text
path_3_external_custom_adapter/
├── 01_source/
│   └── inbound/
│       ├── CLIENT-DATASET-EXAMPLE-001/
│       └── QPDS-PACKAGE-001/
├── 02_signals/
├── 03_dataset/
│   └── normalized/
├── 04_state1_package/
├── 05_runs/
├── 06_review/
└── 07_logs/
    └── onboarding_logs/
```

### Role

* external dataset onboarding
* normalization into governed structures
* containment within STATE_3
* provenance preservation

---

## scripts/

```text
scripts/
└── runtime/
```

### Role

* execution entrypoints
* runtime signal generation
* lifecycle orchestration scripts

---

## shared/

```text
shared/
├── configs/
│   ├── adapter_profiles/
│   ├── extensions/
│   ├── mappings/
│   └── normalization_rules/
├── models/
│   ├── evaluation/
│   └── qpathformer/
├── registry/
│   └── run_references/
├── runtime/
│   └── signal_references/
├── schemas/
│   ├── access-mode/
│   ├── adapter/
│   ├── datasets/
│   └── external/
└── standards/
    └── access_pod/
        └── v1a/
```

### Role

* shared system components
* schemas and validation contracts
* model references and evaluation artifacts
* runtime signal references
* Access-PoD standards layer

---

## Lifecycle Mapping (Across Paths)

All paths follow the same lifecycle structure:

```text
STATE_3 → STATE_2 → STATE_1
```

### Directory Alignment

| Stage   | Directory                      |
| ------- | ------------------------------ |
| STATE_3 | `01_source`, `02_signals`      |
| STATE_2 | `03_dataset`, `06_review`      |
| STATE_1 | `04_state1_package`, `05_runs` |
| Logs    | `07_logs`                      |

---

## Execution Pattern

Each path follows:

```text
source → signals → dataset → package → run → review → logs
```

### Rules

* paths are independent
* lifecycle stages are enforced
* no automatic promotion
* all transitions are explicit

---

## Governance Notes

* all artifacts are lifecycle-bound
* signals are non-authoritative
* datasets require validation and authorization before promotion
* training runs do not grant authority

---

## Repository Characteristics

This repository is:

* fully populated with reviewed artifacts
* reproducible via documented commands
* structured for inspection and validation
* separated by execution, lifecycle, and documentation layers

---

## Final Note

This structure enables:

* deterministic execution
* traceable lifecycle progression
* reproducible validation
* separation of authority from execution

It is designed to function as both:

* a **release artifact set**
* a **controlled execution environment**

---
