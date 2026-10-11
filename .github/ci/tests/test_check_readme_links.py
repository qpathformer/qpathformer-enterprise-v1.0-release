"""Exercise actual tracked Markdown fixtures and broken-link failure cases."""

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_readme_links import check


class ReadmeLinksTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)

    def file(self, name, content, tracked=True):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        if tracked:
            subprocess.run(["git", "-C", str(self.root), "add", "--", name], check=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def test_markdown_links_references_images_and_duplicate_headings(self):
        self.file("README.md", '''# Guide
[overview](#guide)
[first](docs/notes.md#two-cases)
[duplicate](docs/notes.md#two-cases-1)
[named](docs/notes.md#manual-anchor)
[spaced](<papers/Some paper (draft).pdf>)
![chart][figure]

[figure]: images/chart.svg "Chart"

<a href="docs/notes.md#two-cases">HTML link</a>
''')
        self.file("docs/notes.md", '''# Two *cases*
# Two cases
<a id="manual-anchor"></a>
''')
        self.file("papers/Some paper (draft).pdf", "fixture only")
        self.file("images/chart.svg", "fixture only")
        failures, count, local, _ = check(self.root)
        self.assertEqual(failures, [])
        self.assertEqual((count, local), (1, 7))

    def test_missing_case_mismatch_and_untracked_files_fail(self):
        self.file("README.md", "[one](missing.md)\n[two](notes.md)\n[three](untracked.md)")
        self.file("Notes.md", "exists with different case")
        self.file("untracked.md", "exists only on this computer", tracked=False)
        failures, *_ = check(self.root)
        self.assertEqual(len(failures), 3)
        self.assertTrue(all("missing, untracked or has different letter case" in f for f in failures))

    def test_missing_heading_fails_even_when_file_exists(self):
        self.file("README.md", "[read](notes.md#removed-heading)")
        self.file("notes.md", "# Existing heading")
        failures, *_ = check(self.root)
        self.assertEqual(len(failures), 1)
        self.assertIn("#removed-heading is missing", failures[0])

    def test_examples_and_external_urls_are_not_fetched(self):
        self.file("README.md", '''```md
[example](nonexistent.md)
```
`[inline example](another-missing.md)`
[website](https://example.invalid/a)
<https://example.invalid/b>
''')
        failures, _, local, external = check(self.root)
        self.assertEqual((failures, local, external), ([], 0, 2))

    def test_component_readmes_relative_paths_encoded_names_and_setext(self):
        self.file("README.md", "[component](component/#start-here)")
        self.file("component/README.md", "# Start here\n[paper](../papers/Some%20paper.pdf)\n[more](notes.md#underlined)")
        self.file("component/notes.md", "Underlined\n==========")
        self.file("papers/Some paper.pdf", "fixture only")
        failures, count, local, _ = check(self.root)
        self.assertEqual((failures, count, local), ([], 2, 3))

    def test_repository_escape_and_machine_paths_fail(self):
        self.file("README.md", "[escape](../outside.md)\n[local](file:///C:/private/file.md)")
        failures, *_ = check(self.root)
        self.assertEqual(len(failures), 2)

    def test_root_readme_is_required(self):
        failures, *_ = check(self.root)
        self.assertEqual(failures, ["README.md: root README is missing or untracked"])

    def test_symlink_to_outside_repository_fails_without_fragment(self):
        with tempfile.TemporaryDirectory() as outside:
            target = Path(outside) / "paper.pdf"
            target.write_text("fixture only", encoding="utf-8")
            try:
                (self.root / "paper.pdf").symlink_to(target)
            except (OSError, NotImplementedError):
                self.skipTest("symlink creation is unavailable on this system")
            subprocess.run(["git", "-C", str(self.root), "add", "--", "paper.pdf"], check=True,
                           capture_output=True)
            self.file("README.md", "[paper](paper.pdf)")
            failures, *_ = check(self.root)
            self.assertEqual(len(failures), 1)
            self.assertIn("resolves outside the repository", failures[0])


if __name__ == "__main__":
    unittest.main()
