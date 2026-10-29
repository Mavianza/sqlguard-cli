"""Analisis menggunakan parser SQLite, authorizer, dan EXPLAIN QUERY PLAN."""

from __future__ import annotations

from contextlib import closing
from dataclasses import asdict, dataclass
import math
from pathlib import Path
import re
import sqlite3
import time

MAX_SQL_BYTES = 65_536
MAX_PARAMETERS = 1_000


class SqlGuardError(Exception):
    """Kesalahan masukan atau kegagalan pemeriksaan yang dapat dilaporkan."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class PlanStep:
    id: int
    parent: int
    detail: str


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str
    step_id: int
    message: str


@dataclass(frozen=True)
class Report:
    database: str
    plan: tuple[PlanStep, ...]
    findings: tuple[Finding, ...]

    @property
    def warning_count(self) -> int:
        return sum(f.severity == "warning" for f in self.findings)

    def to_dict(self) -> dict:
        return {
            "schema_version": 1,
            "status": "warnings" if self.warning_count else "passed",
            "database": self.database,
            "sqlite_version": sqlite3.sqlite_version,
            "warning_count": self.warning_count,
            "plan": [asdict(step) for step in self.plan],
            "findings": [asdict(finding) for finding in self.findings],
        }


def _first_keyword(sql: str) -> str:
    """Lewati komentar awal; SQLite tetap menjadi parser SQL sesungguhnya."""
    rest = sql.lstrip("\ufeff").lstrip()
    while rest.startswith(("--", "/*")):
        if rest.startswith("--"):
            end = rest.find("\n")
            rest = "" if end == -1 else rest[end + 1 :].lstrip()
        else:
            end = rest.find("*/", 2)
            if end == -1:
                raise SqlGuardError("invalid_sql", "Komentar SQL belum ditutup.")
            rest = rest[end + 2 :].lstrip()
    match = re.match(r"[A-Za-z_]+", rest)
    return match.group().upper() if match else ""


def validate_parameters(parameters: object) -> list | dict:
    if parameters is None:
        return []
    if not isinstance(parameters, (list, dict)):
        raise SqlGuardError("invalid_parameters", "Parameter harus berupa array atau objek JSON.")
    if len(parameters) > MAX_PARAMETERS:
        raise SqlGuardError("invalid_parameters", "Maksimal 1000 parameter dalam satu query.")
    if isinstance(parameters, dict) and not all(isinstance(k, str) and k for k in parameters):
        raise SqlGuardError("invalid_parameters", "Nama parameter harus berupa string yang tidak kosong.")
    values = parameters.values() if isinstance(parameters, dict) else parameters
    for value in values:
        valid = value is None or isinstance(value, (str, bool))
        if type(value) is int:
            valid = -(2**63) <= value < 2**63
        elif type(value) is float:
            valid = math.isfinite(value)
        if not valid:
            raise SqlGuardError("invalid_parameters", "Nilai parameter harus scalar JSON; angka harus finite dan integer dalam rentang 64-bit.")
    return parameters


def interpret_plan(plan: tuple[PlanStep, ...]) -> tuple[Finding, ...]:
    """Aturan indikatif; detail asli selalu disertakan untuk inspeksi manual."""
    findings = []
    for step in plan:
        detail = step.detail.upper()
        constant_scan = re.match(r"SCAN (?:CONSTANT ROW|\d+ CONSTANT ROWS?|\d+-ROW VALUES CLAUSE)\b", detail)
        if detail.startswith("SCAN ") and not constant_scan:
            if " USING " in detail and "INDEX" in detail:
                findings.append(Finding("index_scan", "info", step.id, "Seluruh sumber dipindai melalui index; penggunaan index belum tentu berarti pencarian selektif."))
            else:
                findings.append(Finding("full_scan", "warning", step.id, "Pemindaian seluruh sumber. Periksa selektivitas WHERE dan index jika sumber berukuran besar."))
        if "TEMP B-TREE" in detail:
            findings.append(Finding("temporary_btree", "warning", step.id, "SQLite merencanakan struktur sementara untuk sort, pengelompokan, atau penghapusan duplikat."))
        if re.search(r"\bAUTOMATIC\b.*\bINDEX\b", detail):
            findings.append(Finding("automatic_index", "warning", step.id, "SQLite merencanakan index otomatis. Evaluasi index permanen bila pola query ini sering dipakai."))
        if "CORRELATED" in detail and "SUBQUERY" in detail:
            findings.append(Finding("correlated_subquery", "info", step.id, "Subquery bergantung pada baris query luar; evaluasi biayanya pada data yang representatif."))
    return tuple(findings)


def analyze(database: str | Path, sql: str, parameters: object = None) -> Report:
    if not isinstance(sql, str) or not sql.strip():
        raise SqlGuardError("invalid_sql", "Query SQL tidak boleh kosong.")
    if "\x00" in sql or len(sql.encode("utf-8")) > MAX_SQL_BYTES:
        raise SqlGuardError("invalid_sql", "SQL mengandung NUL atau melebihi 65536 byte.")
    if _first_keyword(sql) not in {"SELECT", "WITH", "VALUES"}:
        raise SqlGuardError("unsafe_sql", "Hanya satu query SELECT, WITH ... SELECT, atau VALUES yang diizinkan.")
    bindings = validate_parameters(parameters)
    path = Path(database).expanduser().resolve()
    if not path.is_file():
        raise SqlGuardError("database_not_found", "Berkas database tidak ditemukan.")

    denied = False
    allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}

    def authorize(action, first, second, db_name, trigger):
        nonlocal denied
        # Load extension tidak diperlukan untuk inspeksi query.
        if action not in allowed or (action == sqlite3.SQLITE_FUNCTION and (second or "").lower() == "load_extension"):
            denied = True
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    try:
        # as_uri mengodekan spasi, #, dan ? agar tidak menjadi opsi URI.
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=1.0)) as connection:
            connection.execute("PRAGMA query_only = ON")
            connection.execute("PRAGMA trusted_schema = OFF")
            connection.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, MAX_SQL_BYTES + 32)
            connection.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, MAX_PARAMETERS)
            connection.setlimit(sqlite3.SQLITE_LIMIT_EXPR_DEPTH, 100)
            connection.setlimit(sqlite3.SQLITE_LIMIT_COMPOUND_SELECT, 50)
            deadline = time.monotonic() + 2.0
            connection.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
            connection.set_authorizer(authorize)
            # Query pengguna tidak dijalankan. Yang dibaca hanya baris rencana.
            rows = connection.execute("EXPLAIN QUERY PLAN " + sql.lstrip("\ufeff"), bindings).fetchall()
    except sqlite3.Error as exc:
        if denied:
            raise SqlGuardError("unsafe_sql", "Query ditolak: memerlukan operasi selain pembacaan atau fungsi yang dibatasi.") from exc
        raise SqlGuardError("sqlite_error", f"SQLite tidak dapat merencanakan query: {exc}") from exc
    plan = tuple(PlanStep(int(row[0]), int(row[1]), str(row[3])) for row in rows)
    return Report(str(path), plan, interpret_plan(plan))
