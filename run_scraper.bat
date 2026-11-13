@echo off
rem Memperbarui semua data untuk site\index.html. Dijalankan setiap hari oleh task Windows
rem "Jobs Seeker refresh" (lihat scripts\register_task.ps1). Log run terakhir: scraper\last_run.log
cd /d "%~dp0"
python scraper\scrape.py > scraper\last_run.log 2>&1
