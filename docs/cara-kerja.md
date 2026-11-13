# Cara kerja

## Alur satu kali run

`python scraper/scrape.py` menjalankan langkah berikut secara berurutan:

1. **Ambil daftar lowongan** dari setiap sumber di tab Jobs (Glints, Kalibrr, JobStreet, LinkedIn, Dealls,
   career site perusahaan). Halaman daftar/pencarian selalu dibaca, karena hanya dari situ terlihat lowongan
   baru dan lowongan yang sudah tutup.
2. **Ambil detail** (deskripsi, jumlah pelamar, deadline, dan lainnya) hanya untuk lowongan yang belum ada
   di cache atau datanya sudah lebih dari 7 hari. Lihat [Cache](#cache).
3. **Saring**: hanya role engineering di Pulau Jawa (atau remote tanpa kota). Lihat
   [Skor dan label](skor-dan-label.md).
4. **Gabungkan duplikat**: lowongan yang sama dari beberapa sumber digabung, dan sumber lainnya ditampilkan
   sebagai "Also on".
5. **Hitung skor**, tandai **NEW**, dan catat **riwayat jumlah pelamar**.
6. Jalankan `programs.py` (tab Programs) dan `remote.py` (tab Remote & freelance).
7. Tulis output ke `site/data/` dan simpan cache.

Kalau satu sumber gagal (situs down, diblokir), sumber lain tetap jalan dan tab yang gagal memakai data
sebelumnya.

## File output (`site/data/`)

| File | Isi |
| --- | --- |
| `jobs.js` | Daftar lowongan tab Jobs: semua yang dibutuhkan card, tanpa deskripsi |
| `jobs-details.js` | Detail per lowongan (deskripsi, timeline, perusahaan, dan lainnya) |
| `remote.js`, `remote-details.js` | Hal yang sama untuk tab Remote & freelance |
| `programs.js` | Data tab Programs |

Website memuat `jobs.js` lebih dulu supaya daftar langsung tampil. File lainnya dimuat di background.
Formatnya `window.NAMA = {...};`, bukan JSON murni, supaya bisa dibuka langsung sebagai file (`file://`)
tanpa server.

Kalau `site/data/` belum ada, website memakai `site/sample/`, yang dibuat oleh `scraper/make_sample.py`.

## Cache

`scraper/cache.json` menyimpan data yang sudah diambil beserta waktunya, supaya tidak diambil ulang:

| Data | Diambil ulang paling sering | Alasan |
| --- | --- | --- |
| Halaman detail lowongan | 7 hari | Bagian paling lama (~1.500 halaman; LinkedIn sengaja 1 halaman per detik) |
| Sumber remote & freelance | 6 jam | Beberapa sumber meminta jumlah request kecil per hari |
| Cek status program | 24 jam | Status program jarang berubah |
| Kurs mata uang | 24 jam | Cukup sekali sehari |

- Request yang gagal tidak disimpan, jadi otomatis dicoba lagi di run berikutnya. Selama itu dipakai salinan
  lama kalau ada.
- Entri yang tidak terpakai selama 30 hari dihapus.
- Hapus `cache.json` untuk memaksa semua data diambil ulang.

## Penggabungan duplikat

Dua lowongan dianggap sama kalau **judul + perusahaan + provinsi**-nya sama. Saat membandingkan judul,
keterangan lokasi dan penempatan diabaikan, misalnya `(Surakarta)`, `(Placement: Jakarta)`, `- Remote`, dan
`[URGENT]`. Jadi "Developer (Surakarta)" dan "Developer (Placement: Surakarta)" dihitung satu lowongan.
Penanda level tetap dibedakan: "Software Engineer II" dan "III" adalah dua lowongan.

Dari setiap kelompok duplikat, yang ditampilkan adalah record dengan data paling lengkap (ada jumlah pelamar,
pengalaman dari deskripsi, gaji, tanggal, deskripsi). Gabungan itu disimpan dengan `key` tetap, yang dipakai
untuk tracking, tombol hide, label NEW, dan riwayat pelamar. Key lama dari versi sebelumnya disimpan sebagai
`aliases`, supaya data tracking yang sudah ada tetap nyambung.

## File lain yang disimpan scraper

| File | Isi |
| --- | --- |
| `scraper/seen.json` | Kapan setiap lowongan pertama dan terakhir terlihat. Dasar label **NEW**. Lowongan yang 60 hari tidak terlihat dilupakan. |
| `scraper/history.json` | Jumlah pelamar/bid dari waktu ke waktu. Titik baru dicatat kalau angkanya berubah atau titik terakhir sudah seminggu. Disimpan 60 hari. |
| `scraper/cache.json` | Cache, lihat di atas |
| `scraper/last_run.log` | Output run terakhir dari jadwal harian |

Semua file ini, beserta `site/data/`, tidak ikut di repository.

## Data di browser

Tracking lamaran, lowongan yang disembunyikan, dan bobot skor disimpan di **localStorage** browser, jadi
hanya ada di browser itu. Tombol **Export backup** di tab My applications mengunduh file JSON, dan
**Import backup** memulihkannya (misalnya setelah data browser dihapus atau saat pindah komputer).

## Menjalankan sebagian

| Perintah | Yang diperbarui |
| --- | --- |
| `python scraper/scrape.py` | Semua tab |
| `python scraper/remote.py` | Hanya tab Remote & freelance |
| `python scraper/programs.py` | Hanya tab Programs |
| `python scraper/make_sample.py` | Contoh data di `site/sample/`, dibuat dari `site/data/` |
