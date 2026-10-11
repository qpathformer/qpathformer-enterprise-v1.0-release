# Repository checks

Two GitHub Actions jobs run on every pull request to `main`, every push to
`main`, and manual workflow runs. There are no path filters that could leave a
required check unreported for a documentation-only change.

| Required check | Scope | Limits |
| --- | --- | --- |
| **README links** | Local Markdown links and images in tracked Markdown files whose names contain `README`, ignoring letter case. Checks tracked targets, exact filename case, repository boundaries and Markdown heading or explicit HTML anchors. | Does not test external websites, bare URLs, paths shown as code, links in other documents, or citations inside PDFs and Word files. |
| **JSON syntax** | Every tracked `.json` and `.jsonl` file, ignoring extension case. Checks UTF-8 encoding and strict JSON syntax, including unique object keys and rejection of `NaN` and `Infinity`. JSONL is checked one record line at a time, with the single preserved blank-line exception below. | Does not validate schemas, dataset quality, model behavior, governance meaning, signatures or provenance. JSON inside ZIP archives is not extracted. |

The README check runs offline. It handles inline and reference Markdown links,
images, angle-bracket paths containing spaces and HTML links. External URL
schemes are excluded. Fragment checking applies to Markdown destinations;
PDF fragment syntax is outside this check.

At the initial maintenance baseline, the 22 tracked README files contain
**zero local Markdown links** in this check's scope; 13 external links are
skipped. Many paths appear as code and references as bare URLs. A green README
result therefore does not confirm those references work; review them manually.
These counts describe the starting point, not a required fixed inventory.

The initial JSON baseline contains 233 JSON files and 23 JSONL files containing
6,336 nonblank records. UTF-8 byte-order marks, empty JSONL files and blank
JSONL record lines are rejected, except for this preserved historical fixture:

```text
shared/schemas/access-mode/access_mode_training_governance_reference.example.jsonl
SHA-256: a454bf925a89ce3115c08c3fd6ac07aa7a0232c7305a948e8be8ddd091eb7d9e
```

The original fixture contains blank lines 2 and 4. The checker tolerates those
lines only at this exact path while the complete file remains byte-identical
to the recorded hash. Every nonblank record is still parsed strictly. The
exception does not apply to a copied path, changed fixture or new JSONL file;
it preserves the published source without silently broadening syntax rules.
Do not reformat the historical fixture to make CI pass. Review any proposed
change as separately versioned material.

The syntax checker reads the tracked JSON and JSONL files already present in
the checkout. It does not materialize datasets, run authorization or promotion
tools, generate CSC evidence, download models, load checkpoints, or execute
training. Passing syntax checks does not reproduce the historical experiments.

Both checks read files without rewriting them. Original papers, datasets,
historical outputs, manifests and release assets retain their published
identities. Any new implementation test or experiment requires its own defined
scope and separately recorded results.

## Run locally

From the repository root, using Python 3.12:

```sh
python -m pip install --require-hashes -r .github/ci/requirements.txt
python -m unittest discover -s .github/ci/tests -v
python .github/ci/check_readme_links.py --root .
python .github/ci/check_json.py --root .
```

Pass `--root .` explicitly when invoking either checker from the repository
root. Only Git-tracked paths are examined. Stage intended new files before
checking their links locally so the inventory matches the files available in
CI. The required checks must still pass on the pull request.

The workflow pins actions and Python dependencies, uses a read-only token,
does not persist checkout credentials, and receives no repository secrets. It
uses `pull_request`, not `pull_request_target`. GitHub may require a maintainer
to approve the workflow run for a first-time external contributor.

## Merge requirements

The `main` rules require **README links** and **JSON syntax** from GitHub Actions.
Strict checking requires the pull-request branch to be up to date with `main`.
Failures must be corrected before merging. Human diff review and conversation
resolution remain part of the [contribution workflow](../CONTRIBUTING.md).

If a required job is renamed or removed, coordinate the workflow and ruleset
changes so merging is not blocked waiting for a check that no longer runs.
Tests under `.github/ci/tests/` exercise these maintenance checkers; they are
not tests of the three-path enterprise implementation.

Passing CI is evidence only for these bounded checks. It is not independent
assurance, legal approval, governance authority or production permission.
