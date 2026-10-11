"""Exercise the checker as a user would, against disposable Git repositories."""

from pathlib import Path
import importlib.util
import subprocess
import sys
import tempfile
import unittest


CHECKER = Path(__file__).resolve().parents[1] / "check_json.py"
SPEC = importlib.util.spec_from_file_location("json_checker", CHECKER)
JSON_CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(JSON_CHECKER)
LEGACY_PATH = "shared/schemas/access-mode/access_mode_training_governance_reference.example.jsonl"


class JsonCheckTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        subprocess.run(["git", "init", "--quiet", str(self.root)], check=True)

    def add_file(self, name, contents, tracked=True):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents.encode("utf-8") if isinstance(contents, str) else contents)
        if tracked:
            subprocess.run(["git", "-C", str(self.root), "add", "--", name], check=True,
                           capture_output=True)

    def check(self):
        return subprocess.run([sys.executable, str(CHECKER), "--root", str(self.root)],
                              capture_output=True, text=True, encoding="utf-8")

    def test_valid_json_including_false_zero_arrays_and_large_numbers(self):
        fixtures = {
            "object.json": '{"nested": {"name": "evidence"}, "ok": true}',
            "false.json": "false",
            "zero.json": "0",
            "array.json": '[null, 0, false, "value"]',
            "string.json": '"review"',
            "large-number.json": "1e400",
        }
        for name, contents in fixtures.items():
            self.add_file(name, contents)
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("6 tracked JSON files", result.stdout)

    def test_only_tracked_json_is_checked_and_extension_is_case_insensitive(self):
        self.add_file("nested space/record.JSON", "{}")
        self.add_file("scratch.json", "not JSON", tracked=False)
        self.add_file("notes.txt", "not JSON")
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("1 tracked JSON files", result.stdout)
        self.add_file("nested space/record.JSON", '{"broken":}')
        result = self.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("nested space/record.JSON", result.stderr)

    def test_malformed_json_reports_path_and_line(self):
        self.add_file("examples/broken.json", '{\n  "value": true,\n}')
        result = self.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("examples/broken.json", result.stderr)
        self.assertIn("line 3", result.stderr)

    def test_duplicate_keys_are_rejected_even_when_nested_or_escaped(self):
        self.add_file("duplicate.json", r'{"record": {"name": 1, "\u006eame": 2}}')
        result = self.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("duplicate object key 'name'", result.stderr)

    def test_nan_and_infinity_tokens_are_rejected(self):
        for token in ["NaN", "Infinity", "-Infinity"]:
            with self.subTest(token=token):
                self.add_file("nonfinite.json", '{"score": ' + token + '}')
                result = self.check()
                self.assertEqual(result.returncode, 1)
                self.assertIn(f"{token} is not a JSON number", result.stderr)

    def test_invalid_utf8_and_bom_are_rejected(self):
        for content, expected in [(b'{"name": "\xff"}', "utf-8"),
                                  (b"\xef\xbb\xbf{}", "byte-order mark")]:
            with self.subTest(content=content):
                self.add_file("encoding.json", content)
                result = self.check()
                self.assertEqual(result.returncode, 1)
                self.assertIn(expected, result.stderr)

    def test_all_failures_are_reported(self):
        self.add_file("one.json", "{")
        self.add_file("two.json", "[1,]")
        result = self.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("one.json", result.stderr)
        self.assertIn("two.json", result.stderr)
        self.assertIn("2 of 2", result.stderr)

    def test_empty_scan_does_not_pass_silently(self):
        result = self.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("no tracked JSON/JSONL files found", result.stderr)

    def test_symlink_to_outside_repository_fails(self):
        with tempfile.TemporaryDirectory() as outside:
            target = Path(outside) / "record.json"
            target.write_text("{}", encoding="utf-8")
            try:
                (self.root / "record.json").symlink_to(target)
            except (OSError, NotImplementedError):
                self.skipTest("symlink creation is unavailable on this system")
            subprocess.run(["git", "-C", str(self.root), "add", "--", "record.json"], check=True,
                           capture_output=True)
            result = self.check()
            self.assertEqual(result.returncode, 1)
            self.assertIn("resolves outside the repository", result.stderr)

    def test_jsonl_accepts_crlf_optional_final_newline_and_scalar_records(self):
        self.add_file("values.jsonl", b'{"name": "first"}\r\nfalse\r\n0\r\n[null, 1]\r\n')
        self.add_file("no-final-newline.jsonl", '"last"')
        self.add_file("unicode-line-separator.jsonl", '{"text": "one\u2028two"}\n')
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("0 tracked JSON files and 3 tracked JSONL files", result.stdout)
        self.assertIn("6 JSONL records", result.stdout)

    def test_jsonl_discovery_is_case_insensitive_and_ignores_untracked_files(self):
        self.add_file("nested space/records.JSONL", '{}\n')
        self.add_file("ignored.jsonl", "not JSON", tracked=False)
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("1 tracked JSONL files", result.stdout)
        self.add_file("nested space/records.JSONL", '{}\n{"broken":}\n')
        result = self.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("nested space/records.JSONL", result.stderr)
        self.assertIn("JSONL line 2", result.stderr)

    def test_jsonl_rejects_duplicate_keys_and_nonfinite_literals_per_record(self):
        for record, expected in [('{"x": 1, "x": 2}', "duplicate object key"),
                                 ('{"x": NaN}', "NaN is not a JSON number"),
                                 ('{"x": Infinity}', "Infinity is not a JSON number"),
                                 ('{"x": -Infinity}', "-Infinity is not a JSON number")]:
            with self.subTest(record=record):
                self.add_file("bad.jsonl", '{}\n' + record + '\n')
                result = self.check()
                self.assertEqual(result.returncode, 1)
                self.assertIn("JSONL line 2", result.stderr)
                self.assertIn(expected, result.stderr)

    def test_jsonl_rejects_empty_files_blank_lines_and_extra_final_newline(self):
        for content, expected in [("", "empty JSONL file"),
                                  ("{}\n\n{}\n", "JSONL line 2: blank lines"),
                                  ("{}\r\n \t\r\n", "JSONL line 2: blank lines"),
                                  ("{}\n\n", "JSONL line 2: blank lines")]:
            with self.subTest(content=content):
                self.add_file("blank.jsonl", content)
                result = self.check()
                self.assertEqual(result.returncode, 1)
                self.assertIn(expected, result.stderr)

    def test_jsonl_rejects_invalid_utf8_and_bom(self):
        for content, expected in [(b'{}\n{"name": "\xff"}\n', "utf-8"),
                                  (b"\xef\xbb\xbf{}\n", "byte-order mark")]:
            with self.subTest(content=content):
                self.add_file("encoding.jsonl", content)
                result = self.check()
                self.assertEqual(result.returncode, 1)
                self.assertIn(expected, result.stderr)

    def test_historical_blank_line_exception_requires_exact_path_and_bytes(self):
        legacy_bytes = (CHECKER.parents[2] / LEGACY_PATH).read_bytes()
        self.add_file(LEGACY_PATH, legacy_bytes)
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("preserved historical JSONL blank lines [2, 4]", result.stdout)

        # Identical bytes at another path do not inherit the exception.
        self.add_file("copied.jsonl", legacy_bytes)
        result = self.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("copied.jsonl: JSONL line 2: blank lines", result.stderr)

        # A harmless leading space still changes the pinned bytes, removing it.
        self.add_file(LEGACY_PATH, b" " + legacy_bytes)
        result = self.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn(LEGACY_PATH + ": JSONL line 2: blank lines", result.stderr)

    def test_allowing_historical_blank_lines_never_skips_record_validation(self):
        with self.assertRaisesRegex(ValueError, "JSONL line 3"):
            JSON_CHECKER.parse_jsonl('{}\n\n{"broken":}\n', allow_blank_lines=True)
        with self.assertRaisesRegex(ValueError, "duplicate object key"):
            JSON_CHECKER.parse_jsonl('{}\n\n{"x": 1, "x": 2}\n', allow_blank_lines=True)
        with self.assertRaisesRegex(ValueError, "at least one record"):
            JSON_CHECKER.parse_jsonl('\n\n', allow_blank_lines=True)


if __name__ == "__main__":
    unittest.main()
