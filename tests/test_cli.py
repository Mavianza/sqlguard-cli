import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from sqlguard.demo import create_demo

ROOT = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.db = create_demo(Path(self.temporary.name) / "kuliah.db")

    def run_cli(self, *args, input=None):
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
        return subprocess.run([sys.executable, "-m", "sqlguard", *map(str, args)], cwd=ROOT, input=input, text=True, encoding="utf-8", capture_output=True, timeout=10, env=env)

    def test_version(self):
        result = self.run_cli("--version")
        self.assertEqual(result.returncode, 0)
        self.assertIn("1.0.0", result.stdout)

    def test_indexed_json_named_parameters(self):
        result = self.run_cli("check", self.db, "--file", "examples/indexed.sql", "--params", '{"semester":3}', "--format", "json", "--strict")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "passed")
        self.assertEqual(result.stderr, "")

    def test_warning_exit_default_zero_and_strict_one(self):
        for flags, expected in [((), 0), (("--strict",), 1)]:
            with self.subTest(flags=flags):
                result = self.run_cli("check", self.db, "--file", "examples/unindexed.sql", *flags)
                self.assertEqual(result.returncode, expected)
                self.assertIn("full_scan", result.stdout)
                self.assertIn("temporary_btree", result.stdout)

    def test_stdin_utf8(self):
        result = self.run_cli("check", self.db, "--file", "-", "--format", "json", input="SELECT 'kuliah ✓'")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "passed")

    def test_bom_file(self):
        source = self.db.parent / "q.sql"
        source.write_bytes(b"\xef\xbb\xbfSELECT 1;\r\n")
        result = self.run_cli("check", self.db, "--file", source)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_invalid_utf8_and_file_not_found(self):
        source = self.db.parent / "bad.sql"
        source.write_bytes(b"\xff\xfe")
        for path in [source, self.db.parent / "missing.sql"]:
            with self.subTest(path=path):
                result = self.run_cli("check", self.db, "--file", path, "--format", "json")
                self.assertEqual(result.returncode, 2)
                self.assertEqual(json.loads(result.stdout)["error"]["code"], "input_error")
                self.assertNotIn("Traceback", result.stderr)

    def test_invalid_parameters_json(self):
        for params in ["{bad}", "null", '"text"', "[NaN]", "[[1]]"]:
            with self.subTest(params=params):
                result = self.run_cli("check", self.db, "--query", "SELECT ?", "--params", params, "--format", "json")
                self.assertEqual(result.returncode, 2)
                self.assertEqual(json.loads(result.stdout)["error"]["code"], "invalid_parameters")

    def test_sql_error_json(self):
        result = self.run_cli("check", self.db, "--query", "SELECT * FROM nonexistent", "--format", "json")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["error"]["code"], "sqlite_error")

    def test_write_error_text_to_stderr(self):
        result = self.run_cli("check", self.db, "--query", "DROP TABLE mata_kuliah")
        self.assertEqual(result.returncode, 2)
        self.assertIn("unsafe_sql", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_argument_conflict(self):
        result = self.run_cli("check", self.db, "--query", "SELECT 1", "--file", "-")
        self.assertEqual(result.returncode, 2)

    def test_demo_and_refuse_overwrite(self):
        new = self.db.parent / "baru.db"
        first = self.run_cli("demo", new)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertGreater(new.stat().st_size, 0)
        second = self.run_cli("demo", new)
        self.assertEqual(second.returncode, 2)
        self.assertIn("output_exists", second.stderr)

    def test_oversize_sql_file(self):
        source = self.db.parent / "large.sql"
        source.write_bytes(b"SELECT '" + b"a" * 65536 + b"'")
        result = self.run_cli("check", self.db, "--file", source, "--format", "json")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["error"]["code"], "invalid_sql")


if __name__ == "__main__":
    unittest.main()
