"""Enam skenario CLI nyata, memakai database sementara dan checksum sumber."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def run(*args):
    return subprocess.run([sys.executable, "-m", "sqlguard", *map(str, args)], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=10, env=dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1"))


def main():
    with tempfile.TemporaryDirectory() as temporary:
        db = Path(temporary) / "demo.db"
        demo = run("demo", db)
        assert demo.returncode == 0, demo.stderr
        digest = hashlib.sha256(db.read_bytes()).hexdigest()
        indexed = run("check", db, "--file", ROOT / "examples/indexed.sql", "--params", '{"semester":3}', "--strict", "--format", "json")
        assert indexed.returncode == 0, indexed.stderr
        assert json.loads(indexed.stdout)["warning_count"] == 0
        unindexed = run("check", db, "--file", ROOT / "examples/unindexed.sql", "--strict", "--format", "json")
        assert unindexed.returncode == 1, unindexed.stderr
        assert {f["code"] for f in json.loads(unindexed.stdout)["findings"]} >= {"full_scan", "temporary_btree"}
        invalid = run("check", db, "--query", "SELECT * FROM tidak_ada", "--format", "json")
        assert invalid.returncode == 2
        assert json.loads(invalid.stdout)["error"]["code"] == "sqlite_error"
        write = run("check", db, "--query", "WITH x AS (SELECT 1) DELETE FROM mata_kuliah", "--format", "json")
        assert write.returncode == 2
        assert json.loads(write.stdout)["error"]["code"] == "unsafe_sql"
        assert hashlib.sha256(db.read_bytes()).hexdigest() == digest, "Database berubah saat check"
        print("6/6 skenario lulus: demo, indexed, unindexed, SQL salah, penolakan write, checksum database tetap.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
