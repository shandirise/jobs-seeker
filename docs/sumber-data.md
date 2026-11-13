# Sumber data

## Tab Jobs: lowongan di Pulau Jawa

| Sumber | Cara mengambil | Yang tampil di popup |
| --- | --- | --- |
| Glints | Halaman pencarian (30 hasil pertama per kata kunci) + halaman tiap lowongan | Deskripsi, pendidikan, rentang pengalaman, benefit, deadline, nama recruiter + kapan terakhir online, ukuran/industri/alamat perusahaan |
| Kalibrr | API pencarian publik (kategori "IT and Software") | Deskripsi, jumlah posisi, response rate recruiter, deadline, benefit, info perusahaan |
| JobStreet | API pencarian (kategori ICT, per provinsi) + API detail | Deskripsi, tipe kerja, tanggal kedaluwarsa, highlight |
| LinkedIn | Pencarian publik (tanpa login) + maksimal 250 halaman detail baru per run | Jumlah pelamar, deskripsi, level senioritas, industri |
| Dealls | API publik (kategori IT & Software) + API detail | Jumlah pelamar, jumlah dilihat, skill, benefit, nama + email recruiter, tahapan seleksi, sektor/pendanaan perusahaan |
| Career site perusahaan | Greenhouse, Lever, SmartRecruiters, Workable (daftar di `scraper/companies.json`) | Deskripsi, departemen, tipe kerja |
| Traveloka | API daftar lowongan + halaman tiap lowongan | Deskripsi, departemen, tipe kerja |
| Shopee | API careers.shopee.co.id | Deskripsi, level, departemen |

Perusahaan di `companies.json` saat ini: Xendit, StraitsX, Bank Jago (Greenhouse); Lalamove, GoTo (Lever);
Grab, Cermati, Stockbit, Kata.ai, GudangAda, BukuWarung, Sayurbox, JULO, Pahamify, PasarPolis, Dekoruma
(SmartRecruiters); Ajaib (Workable).

Tidak setiap sumber menyediakan field yang sama, jadi bagian popup yang tidak ada datanya tidak ditampilkan.

## Tab Remote & freelance

| Sumber | Jenis | Catatan |
| --- | --- | --- |
| Himalayas | Remote job | Memakai filter "terbuka untuk Indonesia" milik Himalayas. Daftar negara dan jam kerja ikut ditampilkan. |
| We Work Remotely | Remote job | Lowongan "Anywhere in the World" dan "Asia Only" |
| Jobicy, Working Nomads, Remotive, Remote OK | Remote job | Hanya sedikit yang lolos aturan wilayah |
| Freelancer.com | Proyek freelance | Proyek berbahasa Inggris, non-lokal, dengan skill IT. Budget dan jumlah bid ditampilkan. |

Aturan yang dipakai untuk tab ini (wilayah, bahasa, role) ada di [Skor dan label](skor-dan-label.md#tab-remote--freelance).

## Tab Programs

Info dasar setiap program (syarat, jadwal biasanya, periode terakhir, sumber berita) ditulis manual di
`scraper/programs.json`. Untuk situs yang bisa dibaca, `programs.py` menambahkan status langsung:

| Program | Pengecekan otomatis |
| --- | --- |
| MagangHub Kemnaker | Banner pengumuman + posisi IT di Jawa dari batch terakhir (dicocokkan dengan jurusan) |
| Magenta BUMN | Semua posting magang yang sedang buka |
| CPNS & PPPK | Timeline pengadaan di SSCASN |
| Magang Bakti BCA | Program yang sedang ditampilkan di karir.bca.co.id |
| BRI (BBAP) | Lowongan + deadline di e-recruitment BRI |
| BNI ODP/ADP | Development program BNI di Kalibrr |
| PCPM Bank Indonesia | Halaman angkatan terbaru di bi.go.id |
| Rekrutmen Bersama BUMN | Manual saja (situs tidak bisa dibaca otomatis) |
| ODP Bank Mandiri | Manual saja |

Status program ("Open now", "Upcoming", "Closed", "Status unknown") diambil dari pengecekan langsung kalau
situsnya menyatakan status, atau dari tanggal di `programs.json` kalau tidak. Setiap card menuliskan dasar
statusnya.

## Sumber yang tidak dipakai

| Sumber | Alasan |
| --- | --- |
| Indeed | Memblokir akses otomatis (HTTP 403) |
| Karir.com | Lowongan hanya dimuat lewat JavaScript |
| TopKarir | Situs tidak bisa diakses saat dibuat |
| KitaLulus | Kebanyakan lowongan non-IT |
| Career site Tokopedia | API-nya tidak publik. Lowongan Tokopedia tetap masuk lewat board Lever GoTo, LinkedIn, dan JobStreet. |
| Upwork | Daftar pekerjaan tidak bisa dibaca publik |
