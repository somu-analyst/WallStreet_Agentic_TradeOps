# resume_after_limit.ps1 — relaunch Claude Code in this repo when the usage limit resets.
#
# Usage (from any PowerShell, when a limit lockout message shows its reset time):
#   .\resume_after_limit.ps1 -At "14:30"              # today at 14:30 (or tomorrow if past)
#   .\resume_after_limit.ps1 -At "2026-07-17 09:00"   # explicit date-time
#
# Registers a one-shot Windows scheduled task that opens a terminal in this repo and
# runs 'claude --continue' (resumes the most recent session here). Claude then reads
# docs/NEXT.md (per the CLAUDE.md limit-lockout rule) and continues the task.
# Cancel anytime:  Unregister-ScheduledTask -TaskName ClaudeResume -Confirm:$false
param(
    [Parameter(Mandatory = $true)][string]$At
)

$repo = Split-Path -Parent $MyInvocation.MyCommand.Path
try {
    $when = [datetime]::Parse($At)
} catch {
    Write-Host "Could not parse '$At' - use 'HH:mm' or 'yyyy-MM-dd HH:mm'"
    exit 1
}
if ($when -lt (Get-Date)) { $when = $when.AddDays(1) }   # bare time already past -> tomorrow

$arg = '/c start "" cmd /k "cd /d {0} & claude --continue"' -f $repo
$act = New-ScheduledTaskAction -Execute "cmd.exe" -Argument $arg
$trg = New-ScheduledTaskTrigger -Once -At $when
try {
    Register-ScheduledTask -TaskName "ClaudeResume" -Action $act -Trigger $trg -Force | Out-Null
    Write-Host ("OK: Claude Code will relaunch in {0} at {1} and continue the last session." -f $repo, $when.ToString("yyyy-MM-dd HH:mm"))
    Write-Host "Cancel with: Unregister-ScheduledTask -TaskName ClaudeResume -Confirm:`$false"
} catch {
    Write-Host ("Failed to register task: {0}" -f $_.Exception.Message)
    exit 1
}
