# Mendaftarkan task Windows yang menjalankan run_scraper.bat setiap hari.
# Jika laptop mati pada jamnya, task dijalankan begitu laptop menyala lagi.
#
#   powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1            # jam 07:00
#   powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1 -At 20:00  # jam lain
#
# Menghapus task:  Unregister-ScheduledTask -TaskName "Jobs Seeker refresh"
param(
    [string]$At = "07:00",
    [string]$TaskName = "Jobs Seeker refresh"
)

$root = Split-Path -Parent $PSScriptRoot
$bat = Join-Path $root "run_scraper.bat"

$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c start `"`" /min `"$bat`"" -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Daily -At $At
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 1)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Description "Memperbarui data Jobs Seeker setiap hari ($bat)." -Force | Out-Null

$info = Get-ScheduledTaskInfo -TaskName $TaskName
Write-Output "Task '$TaskName' terdaftar. Jalan berikutnya: $($info.NextRunTime)"
