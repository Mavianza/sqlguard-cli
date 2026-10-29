from contextlib import closing
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest

from sqlguard.core import PlanStep, SqlGuardError, analyze, interpret_plan
from sqlguard.demo import create_demo


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.db = create_demo(Path(self.temporary.name) / "kampus # aman.db")

    def reject(self, sql, code=None, params=None):
        with self.assertRaises(SqlGuardError) as caught:
            analyze(self.db, sql, params)
        if code:
            self.assertEqual(caught.exception.code, code)

    def test_indexed_named_binding(self):
        report = analyze(self.db, "SELECT nama FROM mata_kuliah WHERE semester=:s", {"s": 3})
        self.assertTrue(any("SEARCH" in step.detail and "idx_matkul_semester" in step.detail for step in report.plan))
        self.assertEqual(report.warning_count, 0)

    def test_unindexed_filter_and_order(self):
        report = analyze(self.db, "SELECT nama FROM mata_kuliah WHERE sks=? ORDER BY nama", [3])
        codes = {f.code for f in report.findings}
        self.assertIn("full_scan", codes)
        self.assertIn("temporary_btree", codes)

    def test_cte_recursive_and_comments(self):
        sql = "\ufeff -- contoh\n/* awal */ WITH RECURSIVE x(n) AS (VALUES(1) UNION ALL SELECT n+1 FROM x WHERE n<3) SELECT * FROM x"
        self.assertTrue(analyze(self.db, sql).plan)

    def test_literals_with_semicolons_and_write_keywords(self):
        self.assertTrue(analyze(self.db, "SELECT 'DELETE; DROP TABLE x; --' AS text;").plan)

    def test_values_is_valid_without_scan_warning(self):
        report = analyze(self.db, "VALUES (1), (2), (3)")
        self.assertEqual(report.warning_count, 0)

    def test_primary_key_lookup(self):
        report = analyze(self.db, "SELECT * FROM mata_kuliah WHERE id=?", [2])
        self.assertEqual(report.warning_count, 0)
        self.assertTrue(any("PRIMARY KEY" in step.detail for step in report.plan))

    def test_syntax_and_unknown_schema_rejected(self):
        for sql in ["SELECT FROM", "SELECT * FROM unknown_table", "SELECT missing FROM mata_kuliah"]:
            with self.subTest(sql=sql):
                self.reject(sql, "sqlite_error")

    def test_empty_oversize_nul_and_unclosed_comment(self):
        for sql in ["", " \n", "-- comment", "/* unclosed", "SELECT '\x00'", "SELECT '" + "a" * 65536 + "'"]:
            with self.subTest(sql=sql[:30]):
                self.reject(sql)

    def test_multiple_statements_rejected_without_mutating_database(self):
        before = hashlib.sha256(self.db.read_bytes()).digest()
        self.reject("SELECT 1; DELETE FROM mata_kuliah", "sqlite_error")
        self.assertEqual(before, hashlib.sha256(self.db.read_bytes()).digest())

    def test_write_admin_and_transaction_commands_rejected(self):
        before = self.db.read_bytes()
        commands = ["DELETE FROM mata_kuliah", "UPDATE mata_kuliah SET sks=1", "INSERT INTO mata_kuliah VALUES(9,'X','X',1,1)", "DROP TABLE mata_kuliah", "PRAGMA writable_schema=ON", "PRAGMA journal_mode=WAL", "VACUUM", "ATTACH DATABASE ':memory:' AS other", "BEGIN", "EXPLAIN SELECT 1"]
        for sql in commands:
            with self.subTest(sql=sql):
                self.reject("/* comment */ " + sql, "unsafe_sql")
        self.assertEqual(before, self.db.read_bytes())
        self.assertFalse(Path(str(self.db) + "-wal").exists())

    def test_with_update_is_blocked_by_sqlite_authorizer(self):
        before = self.db.read_bytes()
        self.reject("WITH x AS (SELECT 1) UPDATE mata_kuliah SET sks=1", "unsafe_sql")
        self.assertEqual(before, self.db.read_bytes())

    def test_load_extension_rejected(self):
        self.reject("SELECT load_extension('not-an-extension')", "unsafe_sql")

    def test_missing_database_not_created(self):
        missing = self.db.parent / "missing.db"
        with self.assertRaises(SqlGuardError) as caught:
            analyze(missing, "SELECT 1")
        self.assertEqual(caught.exception.code, "database_not_found")
        self.assertFalse(missing.exists())

    def test_corrupt_database_handled(self):
        bad = self.db.parent / "broken.db"
        bad.write_text("not SQLite", encoding="utf-8")
        with self.assertRaises(SqlGuardError):
            analyze(bad, "SELECT * FROM mata_kuliah")

    def test_invalid_bindings(self):
        for params in [1, "abc", [[1]], {"s": {"nested": 1}}, [2**63], [float("inf")], [float("nan")], [0] * 1001]:
            with self.subTest(params=str(params)[:20]):
                self.reject("SELECT ?", "invalid_parameters", params)

    def test_missing_binding_reported(self):
        self.reject("SELECT :missing", "sqlite_error")

    def test_scalar_bindings(self):
        for value in [None, True, "teks", 2**63 - 1, -(2**63), 1.5]:
            with self.subTest(value=value):
                self.assertTrue(analyze(self.db, "SELECT ?", [value]).plan)

    def test_successful_analysis_preserves_database_and_data(self):
        before = self.db.read_bytes()
        # Recursive query tak berbatas akan terus berjalan jika benar-benar dieksekusi.
        report = analyze(self.db, "WITH RECURSIVE x(n) AS (VALUES(1) UNION ALL SELECT n+1 FROM x) SELECT * FROM x")
        self.assertTrue(report.plan)
        self.assertEqual(before, self.db.read_bytes())
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM mata_kuliah").fetchone()[0], 6)

    def test_plan_format_and_severity_rules(self):
        plan = (
            PlanStep(1, 0, "SCAN t USING COVERING INDEX idx"),
            PlanStep(2, 0, "SEARCH b USING AUTOMATIC PARTIAL COVERING INDEX (id=?)"),
            PlanStep(3, 0, "CORRELATED SCALAR SUBQUERY 1"),
            PlanStep(4, 0, "UNION USING TEMP B-TREE"),
            PlanStep(5, 0, "SCAN CONSTANT ROW"),
            PlanStep(6, 0, "SCAN 3 CONSTANT ROWS"),
            PlanStep(7, 0, "SCAN 3-ROW VALUES CLAUSE"),
        )
        findings = interpret_plan(plan)
        self.assertEqual([(f.code, f.severity) for f in findings], [("index_scan", "info"), ("automatic_index", "warning"), ("correlated_subquery", "info"), ("temporary_btree", "warning")])

    def test_report_json_shape(self):
        data = analyze(self.db, "SELECT * FROM mata_kuliah").to_dict()
        self.assertEqual(data["schema_version"], 1)
        self.assertEqual(data["status"], "warnings")
        self.assertEqual(data["warning_count"], 1)
        self.assertEqual(set(data["plan"][0]), {"id", "parent", "detail"})

    def test_demo_never_overwrites_existing_file(self):
        before = self.db.read_bytes()
        with self.assertRaises(SqlGuardError) as caught:
            create_demo(self.db)
        self.assertEqual(caught.exception.code, "output_exists")
        self.assertEqual(before, self.db.read_bytes())

    def test_demo_parent_missing(self):
        with self.assertRaises(SqlGuardError) as caught:
            create_demo(self.db.parent / "missing" / "demo.db")
        self.assertEqual(caught.exception.code, "demo_error")


if __name__ == "__main__":
    unittest.main()
