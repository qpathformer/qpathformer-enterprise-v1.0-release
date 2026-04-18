# Path 1 — TR Corpus Reference

---

## Purpose

Path 1 implements **deterministic dataset construction from the internal TR corpus**.

It provides:

* governed signal extraction
* structured dataset formation
* controlled progression to STATE_1
* local validation via LoRA fine-tuning

This path operates **without runtime model dependency**.

---

## Flow

```text
01_source → 02_signals → 03_dataset → 04_state1_package → 05_runs → 06_review → 07_logs
```

---

## Directory Structure

### `01_source/`

* TR documents
* corpus snapshot
* readme references

---

### `02_signals/`

* governed signal extraction outputs
* structured TR-derived signals

---

### `03_dataset/`

* dataset construction outputs
* manifests and checkpoint datasets

---

### `04_state1_package/`

* STATE_1 training-preparation package
* freeze outputs

**Primary package:**

```text
04_state1_package/QPDS-TR-STRICT-ID3-001/
```

---

### `05_runs/`

* local LoRA fine-tuning runs
* checkpoints and model outputs

---

### `06_review/`

* reserved for review notes and validation outputs

---

### `07_logs/`

* run logs for training and execution
* traceability of Path 1 operations

---

## Execution

Primary scripts are located in:

```text
../scripts/
```

Path 1 is executed via:

* TR signal extraction
* dataset build scripts
* STATE_1 packaging
* local validation runs

---

## Lifecycle Position

Path 1 progresses deterministically through:

* STATE_3 (signal extraction)
* STATE_2 (dataset formation readiness)
* STATE_1 (training-preparation package)

### Rules

* no runtime-generated signals
* no external data ingestion
* no automatic promotion outside controlled flow

---

## Characteristics

* deterministic and reproducible
* corpus-bound (internal TR only)
* governance-aligned signal extraction
* controlled dataset formation

---

## Notes

* this path serves as the **baseline reference dataset pipeline**
* outputs are pre-generated in the release
* execution is optional for review but retained for reproducibility

---
