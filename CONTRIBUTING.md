# Contributing to Q-Pathformer Enterprise v1.0

The [published v1.0 enterprise release](https://github.com/qpathformer/qpathformer-enterprise-v1.0-release/releases/tag/v1.0-qpathformer-enterprise)
is a preserved three-path reference snapshot with historical execution records.
Use the [documentation index](docs/README.md) to understand the architecture,
execution guidance and recorded results before proposing a change.

Later repository maintenance can add clarification, errata and review tooling.
It does not revise the original papers, rerun historical experiments, rebuild
sealed packages or publish a replacement release. Changes to the implementation
or release claims belong in a clearly versioned proposal with new evidence.

## Normal change workflow

1. **Create a focused branch from current `main`.** For example, use
   `docs/clarify-path2-evidence`. Contributors without write access can propose
   changes from a fork, subject to the applicable terms. Keep the published
   packages and preserved evidence separate from the working checkout.
2. **Prepare the change and identify its provenance.** Preserve original
   papers, artifacts, licence notices and attribution. Use errata, supplementary
   guidance or separately versioned additions for corrections. Identify any
   third-party material and confirm that you have permission to submit it.
3. **Check the work locally, then push the branch.** Follow
   [Repository checks](.github/CHECKS.md), inspect the complete diff and record
   relevant manual checks. Ordinary maintenance checks do not execute model
   training, runtime signal generation or the three-path pipelines.
4. **Open a draft pull request to `main`.** Describe the problem, resulting
   behavior, affected files, provenance and validation. Distinguish maintenance
   guidance from a future release proposal. Do not upload private datasets,
   credentials or restricted third-party content.
5. **Complete review and resolve feedback.** Mark the pull request ready when
   complete. Review its diff, rights and attribution, preservation of original
   material, and both required check results. Resolve conversations. If `main`
   advances, update the branch and wait for the checks to pass again.
6. **Merge deliberately.** A maintainer performs the merge after review and
   passing checks. Squash merging is suitable for a focused change. Delete the
   completed working branch if no longer needed, then update local `main`.
   A merge is not publication, independent assurance or production authorization.

## Required checks and merge rules

Changes to `main` must use a pull request. The exact required GitHub Actions
checks are **README links** and **JSON syntax**, with the proposed branch up to
date with `main` and review conversations resolved. Force pushes and deletion
of `main` are blocked, and no bypass actors are configured.

The current single-maintainer workflow requires **zero approving reviews**;
the maintainer can merge their own pull request after the other conditions are
met. This creates a visible proposal and review record without representing
independent approval. Human review remains required by this workflow. An
independent approval requirement can be introduced when another eligible
reviewer is available.

The checks cover local Markdown links in tracked README files and strict
syntax of tracked JSON and JSONL records, with one documented, hash-bound
exception for blank lines in an unchanged historical fixture. They do not
verify schema agreement,
data quality, governance meaning, provenance or preservation of every original
file. External websites, paths shown as code, and links in other documents need
manual review. See [Repository checks](.github/CHECKS.md) for local commands and
the precise coverage limits.

## Licences and contribution scope

Read [LICENSE](LICENSE) and the
[Q-Pathformer Platform License 1.0](QPATHFORMER-PLATFORM-1.0.txt) before proposing
material. The existing terms distinguish research, evaluation and internal
development from derivative-build distribution and production or commercial
integration. This guide adds no licence grant and changes none of those terms.
Public availability or acceptance of a pull request does not itself provide
additional redistribution or production rights.

Identify the source and applicable terms of contributed code, data and
documents. Preserve attribution and copyright notices, and disclose material
adapted from elsewhere. Explain any AI-assisted contribution so a maintainer
can review its sources, accuracy and suitability. Do not remove or bypass
governance safeguards as part of a proposed change.

The preserved Access-PoD v1a material has its own
[MIT licence](shared/standards/access_pod/vendor/access-pod-artifacts-core/v1a/LICENSE).
Keep that upstream material and its notices unchanged. The maintenance helpers
under `.github/ci/` separately carry their own scoped
[MIT notice](.github/ci/LICENSE), retained from the Access PoD helpers from
which they were adapted. Neither notice relicenses the Q-Pathformer platform,
papers or other artifacts. Existing file-specific terms remain applicable.

## Preserve published and historical records

- Keep `v1.0-qpathformer-enterprise` at its published commit. Its tag protection
  prevents movement and deletion; it does not make release assets immutable.
- Do not replace, delete or regenerate published ZIP packages, checksums,
  manifests or other release assets as part of repository maintenance.
- Keep original papers, datasets, generated artifacts, model-run records,
  checkpoints, CSC observations and provenance byte-for-byte unchanged.
  Maintenance CI does not download models or rerun those workflows.
- Record any later experiment separately with its own inputs, environment,
  commands and outcome. Do not overwrite historical results, relabel them as a
  new run or use a historical success as evidence for changed code.
- Preserve original manifests and hashes as records of their named snapshots.
  Do not refresh them to include later contribution guides or CI files.
- Prepare future editions through a separate versioned review and publication
  process, with new evidence, integrity records and an explicitly reviewed
  distribution scope.

For every pull request, check that the diff contains only the intended changes.
Later publication work must also compare the existing release tag and asset
identities and hashes before and after the work.
