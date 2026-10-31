# Q-Pathformer Enterprise v1.0

**Governed Dataset Lifecycle, Execution Routing, and CSC Evidence System**

---

Q-Pathformer Enterprise v1.0 is a three-path reference release for governed dataset preparation, runtime signal routing and execution-bound evidence. It includes recorded outputs that can be inspected before running any pipeline, with separate guides for source-first lifecycle processing, runtime signals and external-data containment. The release records what each route reached and the controls that limited further progression.

## Start here

| Goal | Reading destination |
| --- | --- |
| Find architecture, execution guides and papers | [Documentation index](docs/README.md) |
| Inspect the recorded route outcomes | [QPATH-RUN-001 — Path 1, 2 and 3 results](<docs/orientation/results_docs/QPATH-RUN-001 — Path 1,2 & 3 Run Results.md>) |
| Interpret CSC evidence and its limits | [QPATH-CSC-001 — CSC results](<docs/orientation/results_docs/QPATH-CSC-001 - Q-Pathformer Enterprise Run Results.md>) |
| Download the preserved snapshot | [Published v1.0 release](https://github.com/qpathformer/qpathformer-enterprise-v1.0-release/releases/tag/v1.0-qpathformer-enterprise) |

## Recorded routes

| Route | Recorded scope | Execution guide |
| --- | --- | --- |
| Path 1, deterministic corpus | STATE_1 package and controlled local validation. | [Path 1](docs/execution/path_1_tr_corpus_reference_commands.md) |
| Path 2, source-first | Review, promotion, handoff, freeze, registry and controlled local validation; documented release default. | [Source-first route](docs/execution/path_2_access_mode_canonical_source_first_commands.md) |
| Path 2, runtime | STATE_2 review with a promotion hold: one candidate in the recorded session, below the grouped threshold of four. | [Runtime route](docs/execution/path_2_access_mode_canonical_runtime_signal_commands.md) |
| Path 3, external input | STATE_3 containment and normalisation; no promotion or training run in v1.0. | [External-input route](docs/execution/path_3_external_custom_adapter_commands.md) |

These are historical outcomes reported in QPATH-RUN-001, not reruns performed for this README update. Use the [Path 2 route selector](docs/execution/path_2_access_mode_canonical_commands.md) to choose the source-first or runtime commands.

The CSC results identify Path 2 as their evidence source; no CSC session output in this release is derived from Path 1 or Path 3. The record separates mapper-driven finance/healthcare baselines, curated public/AI examples and historical comparisons. Their interpretation limits and the standards-review status below remain applicable.

## System Mental Model

This enterprise release provides dataset lifecycle and execution references. Signals are contained in STATE_3, candidate datasets are reviewed in STATE_2, and approved preparation routes can produce STATE_1 packages. The routes have distinct recorded outcomes and do not automatically progress through every stage.

Lifecycle readiness, execution, validation and authorisation remain separate. Outputs are evidence for external review and do not transfer governance authority into the system.

---

## Overview

This repository is the **v1.0 enterprise reference release** of the Q-Pathformer system integrated with the Access-PoD governance model.

It provides a **fully populated, reviewable artifact set** demonstrating:

- deterministic dataset construction (Path 1)  
- source-first processing and a separate runtime signal route (Path 2)
- external dataset onboarding and containment (Path 3)  
- execution-bound CSC evidence outputs

The repository includes:

- pre-generated lifecycle artifacts across all three paths  
- reproducible execution guidance under `docs/execution/`  
- architecture and governance references under `docs/architecture/`  
- CSC results and run records under `docs/orientation/`  

This release is designed for:

- **inspection** — artifacts can be reviewed directly  
- **validation** — lifecycle structure and traceability can be verified  
- **reproducibility** — execution flows can be rerun if required  

It is not a model distribution, but a **controlled system snapshot** showing how governed datasets, signals, and evidence are produced.

---

## Core Documents

This release is anchored by four primary reference documents:

* **APOD-TR-008** — Q-Pathformer Execution Routing Model
* **APOD-TR-009** — CSC Session Model and Execution-Bound Assurance
* **APOD-TR-009-R** — CSC Results and Evidence Profiles
* **QPATH-RUN-001 / QPATH-CSC-001** — Execution and Results Records

Together, these documents provide the authoritative reference for:

* execution behavior (**how signals are produced**)  
* CSC interpretation (**how signals are understood**)  
* results and evidence (**what the system outputs**)  
* trace records (**how runs are captured and verified**)  

These documents are included under `docs/orientation/` and represent the formal reference layer for this release.

---

## Standards Review Status

This release aligns with the Access-PoD TR document set as a:

- **Public Review Draft (Standards Exploration)**
- **Execution-bound, evidence-producing system**
- **Structured but evolving assurance model**

In this release:

- CSC is implemented as an **execution-bound, telemetry-derived assurance artifact**  
- outputs are **session-scoped and run-scoped evidence snapshots**  
- the assurance model remains **continuous and evolving**  

This release does not represent:

- a finalized standard  
- a certification framework  
- a fully matured assurance model  

Instead, it provides a **working reference implementation** for interpreting CSC from governed execution evidence.

> CSC outputs are **evidence-bound and context-specific**, not final or fixed certification states.

---

## Three-Path System

The repository is organized around three governed dataset pathways:

### Path 1 — TR Corpus Reference
- deterministic TR corpus → dataset pipeline  
- no runtime model dependency  
- produces controlled STATE_1 training-preparation outputs  

---

### Path 2 — Access-Mode Lifecycle

The [source-first route](docs/execution/path_2_access_mode_canonical_source_first_commands.md) starts from the populated `01_source` ID_3 freeze bundle and is the documented release default. Its recorded run passed review, promotion, handoff, freeze, registry and controlled local validation.

The [runtime route](docs/execution/path_2_access_mode_canonical_runtime_signal_commands.md) generates signals under `02_signals/runtime_generated/` and does not consume that `01_source` bundle. Its recorded session passed STATE_2 review with one candidate, then held before STATE_1 because promotion required four grouped candidates (`min_candidates = 4`). Review success alone did not establish promotion eligibility.

---

### Path 3 — External / Custom Adapter
- external dataset ingestion and normalization  
- provenance-preserving containment  

**v1.0 scope:**
- operates as **ingestion + normalization only**  
- all outputs remain in **STATE_3**  
- no candidate formation, promotion, or training runs  

Each path operates independently but follows the same governed lifecycle.

---

## Lifecycle Model

The paths share lifecycle vocabulary; their recorded outcomes do not all reach STATE_1:

- **STATE_3** — containment  
- **STATE_2** — validation  
- **STATE_1** — training preparation  

### Rules

- progression is **explicit and gated**  
- no automatic promotion occurs  
- lifecycle state reflects **readiness, not authority**  
- **STATE_1 does not imply training authorization**

---

## Repository Structure

Top-level layout:

```
docs/
scripts/
shared/
path_1_tr_corpus_reference/
path_2_access_mode_canonical/
path_3_external_custom_adapter/
changes/
```

### Key Roles

* `docs/` → documentation entry point (architecture, execution, orientation)
* `scripts/` → execution entrypoints (PowerShell + Python)
* `shared/` → schemas, configs, registries, runtime, models
* `path_*` → lifecycle implementation paths

---

## Documentation (`docs/`)

The `docs/` folder is the **reviewer-facing entry point**.

### `architecture/`

* repository structure and system layout
* Access-PoD v1a integration audit
* baseline Q-Pathformer architecture reference

### `execution/`

* runnable command guides for each path
* lifecycle flows (source-first, runtime, onboarding)
* CSC generation commands

### `orientation/`

* TR-008 and TR-009 documents
* release results (TR-009-R, RUN-001)
* Markdown sources for trace and results

---

## Execution

Execution entry points are under:

```
scripts/
```

### Execution Behavior

* paths are run independently
* lifecycle stages are enforced per path
* outputs are written into path-local stage folders

Command references are located in:

```
docs/execution/
```

---

## Execution and Artifact State

This release is **pre-populated with reviewed artifacts**.

This means:

* `path_1` contains corpus, dataset, package, and validation outputs
* `path_2` contains source-first lifecycle/promotion outputs and separately identified runtime review/hold outputs
* `path_3` contains onboarding and normalization outputs (STATE_3 containment only in v1.0)

Reviewers can:

* inspect artifacts directly without rerunning pipelines
* validate structure and traceability
* use execution docs only for reproducibility

---

## System Layer Model

The repository is organized into **distinct interpretation layers**.

| Layer | Role in this Repository |
|------|------------------------|
| Execution | how artifacts are produced (scripts, path workflows) |
| Lifecycle | where data sits (`STATE_3 → STATE_2 → STATE_1`) |
| Interpretation | how signals are understood (APOD-TR-009) |
| Results | what outputs are expressed (APOD-TR-009-R) |
| Evidence | how runs are recorded (RUN / CSC records) |
| Documentation | how the system is navigated (`docs/`) |

### Reading Guidance

- **Execution** explains how artifacts were created  
- **Lifecycle** explains their current state  
- **Interpretation** explains meaning without asserting authority  
- **Results and Evidence** show what was produced and recorded  

No single layer implies:

- correctness  
- approval  
- authorization  

All layers must be read **together**.

---

## Governance Posture

This repository is a **reference implementation release**.

It is explicitly:

* **non-authoritative**
* **non-certifying**
* **evidence-producing**

It does not:

* grant training authorization
* define compliance or certification
* assign governance authority

All outputs are:

* lifecycle-bound
* evidence-based
* subject to external interpretation

---

## Access-PoD Integration

The Access-PoD `v1a` release is included as a **preserved standards layer**:

* located under `shared/standards/`
* not modified within this repository
* used as a contract layer for CSC artifacts

### Integration Approach

* **preserve-and-bridge**, not rewrite
* enterprise execution produces evidence
* Access-PoD defines external structure

---

## Example Artifacts Disclaimer

Some files in this repository are provided as:

* example artifacts (`*.example.json`)
* generated demonstration outputs (`*.generated.json`)

These may include:

* placeholder values (e.g., hashes)
* simplified metadata
* non-production values

They are included for:

* schema validation
* lifecycle demonstration
* reproducibility guidance

They are **not production artifacts**.

---

## Release Reading

The v1.0 release should be understood as:

* a **governed execution system**
* a **lifecycle-controlled dataset framework**
* an **execution-bound CSC evidence model**

It demonstrates:

* how datasets are constructed and validated
* how lifecycle progression is enforced
* how assurance signals emerge from execution

without transferring authority into the system.

---

## Notes

* the published tag identifies the preserved release snapshot; `main` may include later documentation maintenance
* example inputs are included for reproducibility
* execution paths are independently runnable

---

## Shared Release Notes

* `shared/models/` retains model references and validation artifacts
* `shared/models/evaluation/` retains benchmark summaries and run manifests
* `shared/standards/` contains the preserved Access-PoD v1a layer
* for full documentation entry, start at:

```
docs/README.md
```

---

## Release

[View GitHub Release (v1.0)](https://github.com/qpathformer/qpathformer-enterprise-v1.0-release/releases/tag/v1.0-qpathformer-enterprise)

It is not a model distribution, but a **controlled system snapshot** showing how governed datasets, signals, and evidence are produced.

The published tag and release assets preserve the **sealed reference state**. Later README and maintenance updates on `main` do not revise that snapshot, its papers or its recorded results.

CSC in this release is **execution-bound and evolving**.  
Outputs are **bounded evidence artifacts within a continuous assurance model**, not final or fixed certification states.
