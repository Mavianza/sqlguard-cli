"""Antarmuka baris perintah SqlGuard."""

import argparse
import json
from pathlib import Path
import sys

from . import __version__
from .core import MAX_SQL_BYTES, SqlGuardError, analyze
from .demo import create_demo


def _read_sql(filename: str) -> str:
    if filename == "-":
        data = sys.stdin.buffer.read(MAX_SQL_BYTES + 1)
    else:
        with Path(filename).open("rb") as stream:
            data = stream.read(MAX_SQL_BYTES + 1)
    if len(data) > MAX_SQL_BYTES:
        raise SqlGuardError("invalid_sql", "Berkas SQL melebihi 65536 byte.")
    return data.decode("utf-8-sig")


def _text(report) -> str:
    lines = ["SqlGuard — pemeriksaan rencana SQLite", f"Database: {report.database}", "Rencana:"]
    lines.extend(f"  [{step.id}; induk {step.parent}] {step.detail}" for step in report.plan)
    if not report.plan:
        lines.append("  Tidak ada node rencana yang ditampilkan SQLite.")
    lines.append(f"Temuan: {report.warning_count} peringatan, {len(report.findings) - report.warning_count} informasi")
    lines.extend(f"  {f.severity.upper()} {f.code} (node {f.step_id}): {f.message}" for f in report.findings)
    lines.append("Query pengguna tidak dijalankan. Temuan merupakan indikasi, bukan pengukuran kecepatan.")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Periksa query SQLite dan rencana index tanpa menjalankan query pengguna.")
    parser.add_argument("--version", action="version", version=f"SqlGuard {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo", help="Buat database contoh baru; tujuan yang sudah ada ditolak.")
    demo.add_argument("destination", type=Path)
    check = commands.add_parser("check", help="Periksa satu query pada database yang sudah ada.")
    check.add_argument("database", type=Path)
    source = check.add_mutually_exclusive_group(required=True)
    source.add_argument("--query", help="SQL inline.")
    source.add_argument("--file", help="Berkas SQL UTF-8; gunakan - untuk stdin.")
    check.add_argument("--params", default="[]", help="Array atau objek JSON untuk parameter SQL.")
    check.add_argument("--format", choices=("text", "json"), default="text")
    check.add_argument("--strict", action="store_true", help="Exit 1 jika ada peringatan rencana.")
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            print(f"Database demo siap: {create_demo(args.destination)}")
            return 0
        sql = args.query if args.query is not None else _read_sql(args.file)
        try:
            parameters = json.loads(args.params)
        except (json.JSONDecodeError, ValueError) as exc:
            raise SqlGuardError("invalid_parameters", "--params bukan JSON yang valid.") from exc
        if not isinstance(parameters, (list, dict)):
            raise SqlGuardError("invalid_parameters", "--params harus berupa array atau objek JSON.")
        report = analyze(args.database, sql, parameters)
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2) if args.format == "json" else _text(report))
        return 1 if args.strict and report.warning_count else 0
    except (SqlGuardError, OSError, UnicodeError) as exc:
        code = exc.code if isinstance(exc, SqlGuardError) else "input_error"
        if getattr(args, "format", "text") == "json":
            print(json.dumps({"schema_version": 1, "status": "error", "error": {"code": code, "message": str(exc)}}, ensure_ascii=False))
        else:
            print(f"Gagal [{code}]: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
