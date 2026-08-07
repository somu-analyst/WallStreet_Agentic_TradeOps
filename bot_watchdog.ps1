# bot_watchdog.ps1 — keep the Telegram bot alive.
#
# The scheduled task TelegramBotWatchdog has pointed at this path since it was registered,
# but the file never existed: 115 missed runs, rc=0xFFFD0000 (PowerShell cannot open the
# -File target). So the one thing meant to cover a dead bot was itself dead. Found
# 2026-08-07 while diagnosing "why are Telegram commands not working".
#
# What it does, in order:
#   1. Is a telegram_bot_optimized.py process alive?      -> if yes, nothing to do
#   2. Is the network actually up (DNS for api.telegram.org)? -> if not, DO NOT restart.
#      A wake-from-sleep blip is not a dead bot, and restarting into a dead network just
#      burns a start and loses the job queue. Wait for the next tick instead.
#   3. Otherwise start the bot detached, and log the reason.
#
# Deliberately quiet: appends one line per action to logs\watchdog.log, nothing on success.

$ErrorActionPreference = 'Stop'
$Root   = 'C:\Users\srini\Options_chain_data\NYSE_DATA'
$Script = Join-Path $Root 'telegram_bot_optimized.py'
$LogDir = Join-Path $Root 'logs'
$Log    = Join-Path $LogDir 'watchdog.log'
$Python = 'C:\Users\srini\AppData\Local\Microsoft\WindowsApps\python.exe'

function Write-Log([string]$msg) {
    # Logging must NEVER take the watchdog down. Two overlapping runs both calling
    # Add-Content throw "file is being used by another process", which with
    # $ErrorActionPreference='Stop' killed the whole script (caught in test 2026-08-07).
    # Retry briefly, then give up silently — restarting the bot matters, the log does not.
    try {
        if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }
        $line = "[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg
        for ($i = 0; $i -lt 5; $i++) {
            try { Add-Content -Path $Log -Value $line -Encoding utf8 -ErrorAction Stop; return }
            catch { Start-Sleep -Milliseconds 200 }
        }
    } catch { }
}

try {
    # ---- 1. already running? ----------------------------------------------------------
    # Match on the COMMAND LINE, not the image name: several python.exe processes run here
    # (dashboard, intraday lane), so a bare process check would always look healthy.
    $running = @(Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='python3.13.exe'" |
                 Where-Object { $_.CommandLine -and $_.CommandLine -like '*telegram_bot_optimized.py*' })
    if ($running.Count -gt 0) { exit 0 }        # healthy — stay silent

    # ---- 2. is the network up? --------------------------------------------------------
    $dnsOk = $false
    try { $null = [System.Net.Dns]::GetHostAddresses('api.telegram.org'); $dnsOk = $true } catch { $dnsOk = $false }
    if (-not $dnsOk) {
        Write-Log 'bot down but DNS for api.telegram.org fails - network not up yet, deferring restart'
        exit 0
    }

    # ---- 3. restart -------------------------------------------------------------------
    if (-not (Test-Path $Script)) { Write-Log "cannot restart: $Script missing"; exit 1 }
    if (-not (Test-Path $Python)) { Write-Log "cannot restart: $Python missing"; exit 1 }

    Start-Process -FilePath $Python -ArgumentList $Script -WorkingDirectory $Root `
                  -WindowStyle Hidden | Out-Null
    Start-Sleep -Seconds 12
    $now = @(Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='python3.13.exe'" |
             Where-Object { $_.CommandLine -and $_.CommandLine -like '*telegram_bot_optimized.py*' })
    if ($now.Count -gt 0) { Write-Log "bot was down - restarted OK (pid $($now[0].ProcessId))" }
    else                  { Write-Log 'bot was down - restart attempted but process not found after 12s' }
    exit 0
}
catch {
    Write-Log "watchdog error: $($_.Exception.Message)"
    exit 1
}
