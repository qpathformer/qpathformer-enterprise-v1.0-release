# Path 3 — External / Custom Adapter

---

## Purpose

Path 3 implements **external dataset onboarding and containment** within the Q-Pathformer lifecycle system.

It provides:

* ingestion of external or client datasets
* normalization into governed structures
* lifecycle containment (STATE_3)
* provenance and traceability

This path acts as the **controlled ingestion boundary** for all non-native data.

---

## Flow (Current v1.0)

```text
01_source → 03_dataset (normalized) → 07_logs
```

> Note: Path 3 does **not currently execute a full lifecycle progression** beyond STATE_3.

---

## Directory Structure

### `01_source/`

```text
01_source/inbound/
```

Contains:

* external datasets
* client-provided bundles
* onboarding packages

### Role

* raw intake layer
* no transformation applied
* full source preservation

---

### `03_dataset/`

#### `normalized/`

* normalized datasets aligned to Q-Pathformer schemas
* structured outputs under controlled format

#### `rejected/` (if present)

* invalid or non-compliant inputs
* failed normalization outputs

---

### `07_logs/`

```text
07_logs/onboarding_logs/
```

Contains:

* ingestion logs
* normalization logs
* validation traces

---

## Reserved / Future Layers

The following directories exist for **future lifecycle expansion**:

* `02_signals/` → adapter-level signal extraction (not active)
* `04_state1_package/` → controlled promotion output (not active)
* `05_runs/` → training/validation runs (not active)
* `06_review/` → structured review layer (minimal use)

---

## Lifecycle Position

All Path 3 artifacts remain in:

```text
STATE_3
```

### Rules

* external data is **contained by default**
* no automatic promotion
* no candidate formation
* no training usage

Promotion requires:

* explicit validation (STATE_2)
* authorization
* controlled transformation

---

## Governance Characteristics

* external data is **non-authoritative**
* normalization does not imply trust
* presence does not imply approval
* signals (if generated) remain provisional

---

## Provenance and Containment

Path 3 enforces:

* full source traceability
* transformation logging
* lineage preservation

Core principle:

> External data is **ingested under containment, not trusted**

---

## Validation and Rejection

Datasets may be:

* accepted → `normalized/`
* rejected → `rejected/`

Rejection conditions include:

* schema mismatch
* incomplete structure
* invalid metadata
* governance conflicts

---

## Notes

* this path is **input-facing only** in v1.0
* it does not produce training-ready datasets
* it does not generate CSC evidence directly
* it is foundational for future dataset expansion

---

## Final Position

Path 3 represents:

* the **external interface to the system**
* the **containment boundary for non-native data**
* the **foundation for future lifecycle integration**

It ensures that:

* all external inputs are controlled
* all transformations are traceable
* governance discipline is preserved from ingestion onward

---
