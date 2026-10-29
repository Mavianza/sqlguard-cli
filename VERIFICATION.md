# Hasil pemeriksaan aktual

Dijalankan pada 30 Oktober 2026 untuk rilis awal SqlGuard 1.0.0. Lingkungan lokal Linux; pemeriksaan berikut benar-benar dieksekusi.

| Pemeriksaan | Lingkungan | Hasil |
| --- | --- | --- |
| `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v` | Python 3.12.14, SQLite 3.53.1 | 34 tes lulus, 0 gagal, 0 skipped |
| `PYTHONDONTWRITEBYTECODE=1 python3 tools/smoke.py` | Python 3.12.14, SQLite 3.53.1 | 6/6 skenario CLI lulus |
| `PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -m unittest discover -s tests -v` | Python 3.12.3, SQLite 3.45.1 | 34 tes lulus, 0 gagal, 0 skipped |
| `PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 tools/smoke.py` | Python 3.12.3, SQLite 3.45.1 | 6/6 skenario CLI lulus |
| Build wheel memakai `python -m pip wheel --no-build-isolation --no-deps --no-index <source> --wheel-dir <temp>` | Python 3.12.14, build backend lokal | Wheel `sqlguard_mini_cli-1.0.0-py3-none-any.whl` terbentuk |
| Instalasi wheel ke virtual environment baru memakai `pip install --no-deps --no-index <wheel>` | Direktori sementara di luar source | Berhasil; perintah `sqlguard --version` mengeluarkan `SqlGuard 1.0.0` |
| CLI hasil instalasi: buat demo, lalu periksa `SELECT nama FROM mata_kuliah WHERE id=?` dengan parameter `[3]` dan `--strict` | Virtual environment tersebut | Exit 0; `SEARCH ... USING INTEGER PRIMARY KEY`; 0 peringatan |

Smoke test membuat database demo, memeriksa pencarian dengan index, mendeteksi scan dan temporary b-tree, melaporkan tabel tidak ada, menolak `WITH ... DELETE`, serta membandingkan checksum database setelah seluruh pemeriksaan. Seluruh database pengujian berada di direktori sementara dan dibersihkan.

Tes tambahan memastikan CTE rekursif tanpa batas hanya direncanakan, isi database tidak berubah, perintah administratif ditolak, database hilang tidak dibuat diam-diam, JSON/kode keluar konsisten, dan tujuan database demo yang sudah ada tidak ditimpa.

Format constant scan SQLite 3.45.1 dan 3.53.1 berbeda. Keduanya telah diuji; query `VALUES` tidak diberi peringatan full scan. Raw plan tetap ditampilkan agar pengguna bisa mengecek format yang belum dikenali.

Belum ada pengujian lokal Windows/macOS atau Python selain kedua versi yang tercantum di atas.
