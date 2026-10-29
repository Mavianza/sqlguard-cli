-- Parameter semester menggunakan index yang disertakan database demo.
SELECT kode, nama
FROM mata_kuliah
WHERE semester = :semester;
