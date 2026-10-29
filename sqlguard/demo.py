"""Buat database contoh secara eksplisit; perintah check tetap baca saja."""

from contextlib import closing
from pathlib import Path
import sqlite3

from .core import SqlGuardError

DEMO_SCHEMA = """
CREATE TABLE mata_kuliah (
    id INTEGER PRIMARY KEY,
    kode TEXT NOT NULL UNIQUE,
    nama TEXT NOT NULL,
    sks INTEGER NOT NULL CHECK (sks BETWEEN 1 AND 6),
    semester INTEGER NOT NULL CHECK (semester BETWEEN 1 AND 8)
);
CREATE INDEX idx_matkul_semester ON mata_kuliah(semester);
INSERT INTO mata_kuliah(kode, nama, sks, semester) VALUES
    ('IF101', 'Algoritma dan Pemrograman', 4, 1),
    ('IF201', 'Struktur Data', 4, 2),
    ('IF301', 'Basis Data', 3, 3),
    ('IF302', 'Jaringan Komputer', 3, 3),
    ('IF401', 'Rekayasa Perangkat Lunak', 3, 4),
    ('IF501', 'Kecerdasan Buatan', 3, 5);
"""


def create_demo(destination: str | Path) -> Path:
    path = Path(destination).expanduser().resolve()
    created = False
    try:
        # Exclusive create melindungi database atau berkas yang sudah ada.
        with path.open("xb"):
            pass
        created = True
        with closing(sqlite3.connect(path)) as connection:
            connection.executescript(DEMO_SCHEMA)
            connection.commit()
        return path
    except FileExistsError as exc:
        raise SqlGuardError("output_exists", "Tujuan sudah ada; pilih nama database demo yang baru.") from exc
    except (OSError, sqlite3.Error) as exc:
        if created:
            path.unlink(missing_ok=True)
        raise SqlGuardError("demo_error", f"Database demo tidak dapat dibuat: {exc}") from exc
