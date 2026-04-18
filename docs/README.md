# Documentation — Q-Pathformer Enterprise v1.0

---

## Purpose

This folder is the **primary documentation entry point** for the v1.0 enterprise release.

It is structured to support:

* reviewer navigation
* execution reproducibility
* architecture traceability
* release result interpretation

The structure is intentionally minimal and separated into three functional layers.

---

## Folder Structure

```text
docs/
├── architecture/
├── execution/
└── orientation/
```

---

## Architecture (`architecture/`)

Contains retained architecture references and release-level context.

### Contents

* `minimal_three_path_root_structure.md`
  Defines the live repository layout for the three-path system.

* `access_pod_v1a_release_audit_20260413.md`
  Audit and provenance record for the preserved Access-PoD v1a standards layer.

* `QPATH-ARCH-001 - Q-Pathformer - Multi-state Machine Learning & LLM Training.pdf`
  Baseline architecture reference for the Q-Pathformer platform.

### Role

This layer explains:

* how the system is structured
* how Access-PoD is integrated
* how governance alignment is preserved

---

## Execution (`execution/`)

Contains all **runnable command guides** for the three-path system.

### Path 1 — TR Corpus Reference

* `path_1_tr_corpus_reference_commands.md`
  TR corpus build, dataset generation, packaging, and LoRA validation flow.

---

### Path 2 — Access-Mode Lifecycle

* `path_2_access_mode_canonical_commands.md`
  Path index and route selector.

* `path_2_access_mode_canonical_source_first_commands.md`
  Source-first lifecycle flow (release default).

* `path_2_access_mode_canonical_runtime_signal_commands.md`
  Runtime signal lifecycle flow (`gpt-oss:20b`).

---

### Path 3 — External / Custom Adapter

* `path_3_external_custom_adapter_commands.md`
  External adapter onboarding flow.

* `path_3_client_custom_dataset_commands.md`
  Client custom dataset onboarding flow.

---

### CSC and Support

* `access_pod_csc_commands.md`
  CSC generation and certificate flow.

* `three_path_quick_prompts.md`
  Quick-start prompts for the three-path system.

* `DOWNLOAD_MODEL.md`
  Model references, download links, and runtime configuration guidance.

---

### Role

This layer defines:

* how each path is executed independently
* how lifecycle flows are reproduced
* how CSC outputs are generated

Execution files are designed so:

* each path can be run independently
* flows are not mixed
* reproducibility is deterministic

---

## Orientation (`orientation/`)

Contains **reviewer-facing documents and release results**.

### Core Papers

* `APOD-TR-008 Interaction-Role Signal Exchange.pdf`
  Execution routing and signal exchange model.

* `APOD-TR-009 - Access pod - CSC Session Model & Execution.pdf`
  CSC session model and execution reference.

---

### Release Results

Located under:

```text
orientation/results_docs/
```

Includes:

* `APOD-TR-009-R - Access PoD CSC Results.pdf`
  CSC results release document.

* `QPATH-RUN-001 - Path 1,2, & 3 Run Results.pdf`
  Three-path execution results.

* `QPATH-CSC-001 - Q-Pathformer Enterprise Run Results.md`
  CSC results (Markdown source).

* `QPATH-RUN-001 — Path 1,2 & 3 Run Results.md`
  Run results (Markdown source).

---

### Role

This layer provides:

* interpretation context
* final outputs of execution
* traceable result artifacts

---

## Documentation Layer Model

The documentation is intentionally separated into:

| Layer        | Purpose                                   |
| ------------ | ----------------------------------------- |
| Architecture | system structure and governance alignment |
| Execution    | how to run the system                     |
| Orientation  | what the system produces                  |

This separation ensures:

* no mixing of execution and interpretation
* clear reviewer navigation
* traceable linkage between inputs, execution, and results

---

## How to Use This Folder

### For Reviewers

* start in `orientation/` to understand results
* use `architecture/` to understand system structure
* inspect `path_*` folders in the root for actual artifacts

---

### For Execution / Validation

* start in `execution/`
* follow one path at a time
* do not mix flows between paths

---

### For Reproducibility

* execution commands are deterministic
* paths are independent
* outputs should match repository artifacts when rerun

---

## Execution State

This release is **pre-populated with reviewed outputs**.

* execution does not need to be run for initial review
* artifacts already exist in `path_1`, `path_2`, and `path_3`
* execution docs are retained for validation and reruns only

---

## Notes

* this folder reflects the current release tree
* command files are structured for isolated execution
* older documentation tied to previous layouts has been removed

---

## Final Position

The `docs/` folder is:

* part of the **release surface**
* not auxiliary documentation
* a structured interface between execution, interpretation, and results

It enables:

* inspection
* validation
* reproducibility

without requiring modification of the core system.

---
