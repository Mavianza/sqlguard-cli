-- Kolom nama belum mempunyai index: contoh scan dan sort.
SELECT kode, nama
FROM mata_kuliah
WHERE nama LIKE '%Data%'
ORDER BY nama;
