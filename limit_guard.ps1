# limit_guard.ps1 — Claude Code Stop-hook: near the usage limit, record the reset
# time and self-schedule the resume BEFORE the lockout can bite.
#
# Runs (async) after each Claude turn. Throttled to once per 10 min. When the
# active 5-hour block's tokens cross the threshold:
#   1. writes "⏰ resume after: <block reset time>" at the top of docs/NEXT.md
#   2. registers a one-shot ClaudeResume scheduled task (reset + 3 min) that
#      reopens Claude Code here with --continue
# Threshold: .claude\limit_threshold_tokens.txt (default 80,000,000 ≈ 95% of the
# largest block ever seen on this machine). Tune it there.
$ErrorActionPreference = "SilentlyContinue"
$repo = Split-Path -Parent $MyInvocation.MyCommand.Path

# throttle: at most one real check per 10 minutes
$stamp = Join-Path $env:TEMP "claude_limit_guard.stamp"
if ((Test-Path $stamp) -and ((Get-Date) - (Get-Item $stamp).LastWriteTime).TotalSeconds -lt 600) { exit 0 }
New-Item -ItemType File -Force $stamp | Out-Null

$thrFile = Join-Path $repo ".claude\limit_threshold_tokens.txt"
$threshold = 80000000
if (Test-Path $thrFile) {
    $t = (Get-Content $thrFile -TotalCount 1).Trim()
    if ($t -match '^\d+$') { $threshold = [long]$t }
}

$raw = & npx --yes ccusage@latest blocks --active --json 2>$null | Out-String
$i = $raw.IndexOf("{")
if ($i -lt 0) { exit 0 }
try { $d = ($raw.Substring($i) | ConvertFrom-Json) } catch { exit 0 }
$blk = $d.blocks | Where-Object { $_.isActive } | Select-Object -First 1
if (-not $blk) { exit 0 }
if ([long]$blk.totalTokens -lt $threshold) { exit 0 }

# -- over threshold: record reset time + self-schedule the resume --
# ASCII marker + explicit UTF8 read/write (PS 5.1 default read is ANSI and
# mangles the file's emoji if we round-trip without it).
$reset = ([datetime]$blk.endTime).ToLocalTime()
$line = ("[RESUME AFTER] {0}  (limit-guard: block at {1} tokens >= {2})" -f `
         $reset.ToString("yyyy-MM-dd HH:mm"), [long]$blk.totalTokens, $threshold)
$next = Join-Path $repo "docs\NEXT.md"
if (Test-Path $next) {
    $lines = @(Get-Content $next -Encoding UTF8) | Where-Object { $_ -notmatch '^\s*\[RESUME AFTER\]' }
    Set-Content $next -Value (,$line + $lines) -Encoding UTF8
} else {
    Set-Content $next -Value $line -Encoding UTF8
}

if (-not (Get-ScheduledTask -TaskName "ClaudeResume" -ErrorAction SilentlyContinue)) {
    $when = $reset.AddMinutes(3)
    $arg = '/c start "" cmd /k "cd /d {0} & claude --continue"' -f $repo
    $act = New-ScheduledTaskAction -Execute "cmd.exe" -Argument $arg
    $trg = New-ScheduledTaskTrigger -Once -At $when
    Register-ScheduledTask -TaskName "ClaudeResume" -Action $act -Trigger $trg -Force | Out-Null
}
# tell the user (Stop-hook JSON contract)
$msg = ("Usage limit near ({0:N0} tokens). Reset {1} recorded in NEXT.md; ClaudeResume task scheduled." -f `
        [long]$blk.totalTokens, $reset.ToString("HH:mm"))
Write-Output ('{"systemMessage": "' + $msg.Replace('"', "'") + '"}')
exit 0
