# Skor dan label

## Skor kemudahan (0–100)

Skor menjawab pertanyaan: seberapa mudah lowongan ini didapat oleh fresh graduate? Bobot bawaannya
60 / 25 / 15, dan bisa diubah lewat slider di bagian "How the score works" di website.

| Bagian | Bobot | Poin penuh → nol |
| --- | --- | --- |
| Pengalaman yang diminta | 60 | 0 tahun / fresh grad / magang = 60 · 1 th = 45 · 2 th = 25 · 3 th = 10 · ≥ 4 th = 0 · tidak disebut = 30 |
| Persaingan (pelamar / bid) | 25 | ≤ 25 = 25 · ≤ 50 = 20 · ≤ 100 = 14 · ≤ 200 = 8 · lebih = 3 · tidak diketahui = 12 |
| Kesegaran | 15 | Diposting ≤ 3 hari = 15 · ≤ 7 = 12 · ≤ 14 = 8 · ≤ 30 = 4 · lebih lama = 0 · tidak diketahui = 7 |

Jumlah pelamar hanya tersedia dari LinkedIn, Dealls, dan Freelancer.com (dalam bentuk jumlah bid). Sumber
lain mendapat nilai netral. Kesegaran dihitung pada hari data diambil.

### Dari mana angka pengalaman diambil

Diambil dari sumber pertama yang tersedia, dengan urutan berikut. Popup menampilkan sumber yang dipakai di
baris "How we know".

1. **Field lowongan**: misalnya pengalaman minimal di Glints, atau tanda "open to fresh graduates" di Kalibrr.
2. **Deskripsi**: kalimat seperti "minimal 2 tahun", "3+ years of experience", "fresh graduates are welcome",
   "lulusan baru". Angka yang dekat dengan kata "pengalaman/experience" diutamakan. Angka usia, durasi
   kontrak, dan umur perusahaan diabaikan.
3. **Judul**: Intern/Magang/Trainee = 0, Junior/Entry = 1, Mid = 2, Senior/Lead/Manager/Head = 4 tahun.
4. Kalau tidak ada sama sekali: "not stated".

## Role

**Tab Jobs, hanya engineering**: Fullstack, Data Engineering, QA / Testing, DevOps / Cloud, Mobile, Frontend,
Backend, AI / ML, dan judul umum seperti "Software Engineer / Developer / Programmer". UI/UX, analyst, IT
support, network, security, sales, dan game tidak dimasukkan.

**Tab Remote & freelance, semua bidang IT**: role di atas, ditambah UI/UX & Design, Data & Analytics,
Security, IT Support & SysAdmin, Product & Project (tech), dan Technical Writing.

Role ditentukan dari judul, dan kecocokan pertama yang dipakai. AI / ML dicek setelah role yang lebih
spesifik, supaya "Mobile Developer – AI app" masuk Mobile.

## Lokasi (tab Jobs)

Lowongan dipetakan ke provinsi di Pulau Jawa (DKI Jakarta, Banten, Jawa Barat, Jawa Tengah, DI Yogyakarta,
Jawa Timur) dari nama kota/kabupaten di lokasinya. Lowongan yang hanya menyebut "Indonesia" atau "Remote"
masuk **Remote / unspecified**. Lowongan di luar Jawa dibuang.

## Tab Remote & freelance

Sebuah lowongan masuk kalau memenuhi tiga syarat:

1. **Menerima pelamar dari Indonesia**: worldwide / anywhere, Asia-Pacific, atau Indonesia tercantum di
   daftar negaranya. Lowongan "USA only", "Europe only", yang hanya menyebut zona waktu, atau tanpa
   keterangan wilayah dibuang.
2. **Cukup bahasa Inggris**: lowongan yang mewajibkan bahasa lain (Jerman, Jepang, Mandarin, dan lainnya)
   atau ditulis dalam bahasa lain dibuang.
3. **Role IT**, seperti di atas.

## Label

| Label | Arti |
| --- | --- |
| **NEW** | Lowongan belum ada di run sebelumnya |
| **Remote** | Lowongan remote, atau tanpa kota |
| **Agency / outsourcing?** | Tebakan: nama perusahaan mengandung kata seperti outsourcing, recruitment, staffing, personnel, placement, talent; atau deskripsinya menyebut "for our client", "salah satu klien kami", "placed at the client's site". Alasannya ditampilkan, dan label ini tidak mengubah skor. |
| **Hidden** | Kamu menekan "Not interested" (tampil kalau "Show jobs I hid" dicentang) |

## Gaji

- **Tab Jobs**: gaji dari Glints, Kalibrr, Dealls, dan JobStreet (hanya sebagian lowongan mencantumkannya)
  diubah ke Rupiah per bulan. Filter "Salary at least" memakai **batas atas** rentang gaji, jadi lowongan
  "Rp 4–6 jt" ikut muncul untuk filter ≥ Rp 5 jt.
- **Tab Remote**: gaji dalam mata uang asing diubah ke Rupiah dengan kurs hari itu dari open.er-api.com
  (kalau gagal, dipakai kurs terakhir yang tersimpan). Gaji tahunan dibagi 12, gaji per jam dikali 160 jam.
  Budget proyek freelance ditampilkan dalam Rupiah (untuk seluruh proyek atau per jam) dan tidak ikut
  filter gaji bulanan.

## Tracking dan pengingat

Di tab My applications, lowongan yang di-track (kecuali yang berstatus Accepted/Rejected) diberi tanda:

- merah kalau deadline tinggal **≤ 3 hari**;
- "Deadline passed" kalau deadline sudah lewat;
- "No longer in the latest data" kalau lowongan tidak muncul lagi di data terbaru (kemungkinan sudah ditutup).

Ringkasan jumlahnya tampil di atas daftar dan di label tab.
