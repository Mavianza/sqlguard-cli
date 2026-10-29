# SqlGuard

Alat mini Python + SQL untuk memeriksa query SQLite sebelum dipakai dalam aplikasi atau praktikum. SqlGuard memvalidasi query terhadap schema database asli, menampilkan rencana eksekusi, dan memberi petunjuk tentang scan serta penggunaan index. Dibuat untuk proyek harian 30 Oktober 2026.

## Fitur

- Pemeriksaan satu query `SELECT`, `WITH ... SELECT`, atau `VALUES`, termasuk CTE rekursif dan parameter.
- Deteksi sintaks salah, tabel/kolom tidak ditemukan, dan parameter yang belum diisi melalui parser SQLite.
- Penolakan perintah perubahan data, DDL, PRAGMA, ATTACH, transaksi, serta `load_extension`.
- Rencana asli SQLite, dengan penanda `full_scan`, `temporary_btree`, `automatic_index`, `index_scan`, dan `correlated_subquery`.
- Laporan teks bahasa Indonesia atau JSON; mode `--strict` untuk pemeriksaan di CI.
- Database demo kuliah dan dua berkas query pembanding siap dipakai.
- Berjalan tanpa paket runtime eksternal, server, maupun koneksi internet.

## Persyaratan dan instalasi

Gunakan Python **3.11 atau lebih baru** dengan modul bawaan `sqlite3`. Ekstrak arsip atau clone repository, lalu buka folder proyek. Semua perintah di bawah dapat langsung dijalankan dari folder tersebut; instalasi paket tidak diperlukan.

```sh
python -m sqlguard --version
```

Instalasi sebagai perintah `sqlguard` juga tersedia secara opsional:

```sh
python -m pip install .
sqlguard --help
```

Instalasi ini memakai build backend setuptools; pip dapat mengunduh backend bila belum tersedia. Cara `python -m sqlguard` tidak memerlukan unduhan.

## Menjalankan contoh

Buat database contoh baru. Perintah ini sengaja menulis database; tujuan yang sudah ada selalu ditolak.

```sh
python -m sqlguard demo demo.db
```

Periksa query yang memakai index:

```sh
python -m sqlguard check demo.db --file examples/indexed.sql --params '{"semester":3}' --strict
```

Tanda petik tunggal untuk JSON di atas dapat digunakan di Bash dan PowerShell. Untuk Command Prompt Windows gunakan `--params "{\"semester\":3}"`.

Contoh bagian keluaran pada SQLite 3.53.1; nomor node dan teks rencana dapat berbeda menurut versi:

```text
Rencana:
  [3; induk 0] SEARCH mata_kuliah USING INDEX idx_matkul_semester (semester=?)
Temuan: 0 peringatan, 0 informasi
```

Bandingkan dengan query tanpa index untuk filter dan pengurutan:

```sh
python -m sqlguard check demo.db --file examples/unindexed.sql --strict --format json
```

Temuannya mencakup `full_scan` dan `temporary_btree`, sehingga mode strict menghasilkan exit code `1`. Tanpa `--strict`, query valid tetap menghasilkan exit code `0` walaupun ada peringatan.

SQL inline dan parameter posisi juga didukung:

```sh
python -m sqlguard check demo.db --query "SELECT nama FROM mata_kuliah WHERE id=?" --params '[3]'
python -m sqlguard check demo.db --file - --format json
```

Perintah kedua membaca SQL dari stdin sampai EOF. Berkas SQL dibaca sebagai UTF-8, termasuk BOM; batas ukuran 65.536 byte. Parameter berupa array untuk `?`, atau objek dengan nama tanpa awalan `:` untuk `:nama`. Nilai didukung: string, integer 64-bit, float finite, boolean, dan null. Maksimal 1.000 parameter.

Untuk database sendiri, ganti `demo.db` dengan path database SQLite yang sudah ada. SqlGuard tidak membuat database yang belum ditemukan saat `check`.

## Exit code dan keluaran

| Kode | Arti |
| --- | --- |
| `0` | Query berhasil diperiksa; dengan strict, tidak ada peringatan. |
| `1` | Query valid, tetapi ada peringatan ketika strict diaktifkan. |
| `2` | Masukan/argumen salah, query ditolak, atau database tidak dapat diperiksa. |

JSON hasil pemeriksaan memiliki `schema_version`, `status`, `database`, `sqlite_version`, `warning_count`, `plan`, dan `findings`. JSON kegagalan pemeriksaan memiliki `status: "error"` dan `error.code` serta `error.message`. Kesalahan penggunaan argumen oleh argparse tetap ditulis ke stderr. Keluaran teks yang berhasil ditulis ke stdout; kegagalan teks ke stderr.

## Cara kerja dan batasan

Perintah `check` membuka database memakai URI `mode=ro`, mengaktifkan `query_only`, mematikan `trusted_schema`, lalu memakai authorizer SQLite yang hanya mengizinkan operasi pembacaan yang diperlukan. Program menjalankan `EXPLAIN QUERY PLAN` untuk SQL pengguna, lalu membaca baris rencananya. Program tidak menjalankan query pengguna untuk mengambil hasil data, membuat index, atau mengubah schema.

Temuan merupakan petunjuk, bukan benchmark atau bukti query lambat. Scan sering wajar pada tabel kecil, index scan tetap dapat membaca seluruh index, dan query dengan index belum tentu lebih cepat. SqlGuard tidak menghitung durasi eksekusi, jumlah hasil, maupun ukuran tabel. Raw plan selalu disertakan; aturan pengenalannya dapat memerlukan pembaruan karena format rencana SQLite berubah antarversi.

Lingkupnya SQLite lokal dengan schema yang dipercaya. SqlGuard bukan sandbox untuk file database berbahaya atau extension pihak ketiga. Virtual table yang membutuhkan modul tambahan bisa gagal direncanakan. Database WAL yang sedang aktif dapat memerlukan file pendamping SQLite dan izin direktori yang sesuai; jangan menyalin file `.db` saja dari database yang masih ditulis.

## Pemeriksaan pengembang

```sh
python -m unittest discover -s tests -v
python tools/smoke.py
```

Tes mencakup query berindex, scan/sort, CTE, parameter, format JSON, kode keluar, file UTF-8/BOM, database rusak/hilang, penolakan write, serta checksum database sebelum/sesudah pemeriksaan. `tools/smoke.py` membuat database sementara dan menjalankan enam skenario CLI nyata. Hasil eksekusi yang benar-benar diperoleh tercatat di [VERIFICATION.md](VERIFICATION.md).

## Referensi implementasi

- [SQLite EXPLAIN QUERY PLAN](https://www.sqlite.org/eqp.html)
- [SQLite EXPLAIN dan perilaku saat prepare](https://www.sqlite.org/lang_explain.html)
- [SQLite authorizer](https://www.sqlite.org/c3ref/set_authorizer.html)
- [Python sqlite3](https://docs.python.org/3.12/library/sqlite3.html)

Lisensi MIT.
