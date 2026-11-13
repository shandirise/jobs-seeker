# Konfigurasi

## Menambah career site perusahaan (`scraper/companies.json`)

Perusahaan yang memakai Greenhouse, Lever, SmartRecruiters, atau Workable bisa ditambahkan tanpa mengubah
kode. Tulis **slug** perusahaan di platform itu beserta nama yang ditampilkan:

```json
{
  "greenhouse": { "xendit": "Xendit" },
  "lever": { "GoToGroup": "GoTo (Gojek, GoPay, Tokopedia)" },
  "smartrecruiters": { "grab": "Grab" },
  "workable": { "ajaib": "Ajaib" }
}
```

Slug adalah bagian URL setelah domain platformnya:

| Platform | Contoh URL | Slug |
| --- | --- | --- |
| Greenhouse | `job-boards.greenhouse.io/xendit` | `xendit` |
| Lever | `jobs.lever.co/GoToGroup` | `GoToGroup` |
| SmartRecruiters | `jobs.smartrecruiters.com/Grab` | `grab` |
| Workable | `apply.workable.com/ajaib` | `ajaib` |

Hanya lowongan engineering di Pulau Jawa yang diambil. Traveloka dan Shopee punya situs sendiri, jadi
diambil oleh fungsi khusus di `scrape.py` (`src_traveloka`, `src_shopee`).

## Info program musiman (`scraper/programs.json`)

Perbarui file ini kalau ada pengumuman jadwal baru. Satu program:

```json
{
  "id": "maganghub",
  "name": "MagangHub – Program Magang Nasional",
  "organizer": "Kemnaker (Ministry of Manpower)",
  "category": "Government internship",
  "url": "https://maganghub.kemnaker.go.id/",
  "auto": "maganghub",
  "summary": "National paid internship for fresh graduates ...",
  "eligibility": ["Fresh graduate D3 / D4 / S1, graduated at most 1 year ago", "..."],
  "benefit": "Monthly allowance equal to the local minimum wage",
  "usual_schedule": "Several batches a year",
  "window": { "from": "2026-10-27", "until": "2026-11-04", "label": "Batch 3 participant registration" },
  "note": "Opsional: catatan yang tampil di card",
  "checked": "2026-11-12",
  "sources": ["https://..."]
}
```

| Field | Keterangan |
| --- | --- |
| `auto` | Nama pengecek otomatis di `programs.py` (`maganghub`, `magenta`, `sscasn`, `bca`, `bri`, `bni`, `bi_pcpm`), atau `null` untuk manual saja |
| `window` | Periode pendaftaran terakhir yang diketahui (format `YYYY-MM-DD`, salah satu boleh `null`), atau `null`. Dipakai untuk status kalau pengecek otomatis tidak bisa menentukan status. |
| `checked` | Tanggal info manual terakhir dicek |

Program baru tanpa pengecek otomatis cukup ditambahkan dengan `"auto": null`.

## Pengaturan di kode

| Di mana | Konstanta | Fungsi |
| --- | --- | --- |
| `scrape.py` | `SEARCH_KEYWORDS` | Kata kunci pencarian Glints |
| | `LINKEDIN_KEYWORDS`, `LINKEDIN_PAGES` | Kata kunci dan jumlah halaman pencarian LinkedIn |
| | `LINKEDIN_MAX_DETAILS` | Maksimal halaman detail LinkedIn baru per run (250) |
| | `JOBSTREET_PROVINCES`, `JOBSTREET_MAX_PAGES` | Provinsi dan jumlah halaman JobStreet |
| | `DETAIL_MAX_AGE_HOURS` | Umur maksimal detail di cache (7 hari) |
| | `CATEGORIES`, `NOT_ENGINEERING`, `PROVINCES` | Aturan role dan lokasi tab Jobs |
| `remote.py` | `REMOTE_MAX_AGE_HOURS` | Umur maksimal data sumber remote di cache (6 jam) |
| | `HIMALAYAS_MAX_PAGES`, `FREELANCER_MAX_PROJECTS` | Batas jumlah data yang diambil |
| | `FREELANCER_SKILLS` | Skill Freelancer.com yang dianggap IT |
| | `HOURS_PER_MONTH` | Jam kerja per bulan untuk gaji per jam (160) |
| `programs.py` | `CHECK_MAX_AGE_HOURS` | Umur maksimal hasil cek program (24 jam) |
| `site/index.html` | `REMIND_DAYS` | Batas hari pengingat deadline (3) |

## Jadwal harian (Windows)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1 -At 07:00
```

| Hal | Cara |
| --- | --- |
| Ganti jam | Jalankan ulang skrip dengan `-At` lain. Task lama ditimpa. |
| Hapus jadwal | `Unregister-ScheduledTask -TaskName "Jobs Seeker refresh"` |
| Lihat hasil run terakhir | `scraper/last_run.log` |

Task berjalan saat kamu login, hanya kalau ada internet, dan langsung jalan saat laptop menyala kalau
jadwalnya terlewat.
