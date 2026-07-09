# Register a Windows Task Scheduler job that sends the HMH daily WhatsApp summary at 18:00.
# Run this script ONCE as Administrator to set it up.
#
# Prerequisites:
#   1. Set CRON_SECRET in your .env file (any random string, e.g. "my-secret-123")
#   2. Update $BaseUrl below if your backend runs on a different port.
#   3. Run: powershell -ExecutionPolicy Bypass -File schedule_daily_summary.ps1

param(
    [string]$BaseUrl   = "http://localhost:8000",
    [string]$CronSecret = $env:CRON_SECRET,
    [string]$TaskName  = "HMH-DailySummary-6pm"
)

if (-not $CronSecret) {
    Write-Error "CRON_SECRET is not set. Add it to your .env and pass it via -CronSecret or set the env var."
    exit 1
}

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NonInteractive -Command `"Invoke-WebRequest -Uri '$BaseUrl/api/v1/internal/send-daily-summary' -Method POST -Headers @{'X-Cron-Secret'='$CronSecret'} -UseBasicParsing | Out-Null`""

$trigger = New-ScheduledTaskTrigger -Daily -At "18:00"

$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 2) `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -RunLevel Highest `
    -Force

Write-Host "Task '$TaskName' registered. It will fire daily at 18:00." -ForegroundColor Green
Write-Host "To test immediately: Start-ScheduledTask -TaskName '$TaskName'"
