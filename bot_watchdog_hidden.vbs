' bot_watchdog_hidden.vbs - launch the watchdog with NO console window.
'
' Task Scheduler running powershell.exe under an Interactive logon pops a console window
' every time, and the watchdog fires every 5 minutes, so the user got a visible flash all
' day (reported 2026-08-07). PowerShell's own -WindowStyle Hidden does not prevent this:
' the console is allocated before PowerShell can act on the flag.
'
' WScript.Shell.Run with intWindowStyle=0 never allocates one. bWaitOnReturn=False so the
' launcher exits immediately and Task Scheduler records a clean result.

Dim sh, root, ps1
Set sh = CreateObject("WScript.Shell")
root = "C:\Users\srini\Options_chain_data\NYSE_DATA"
ps1  = root & "\bot_watchdog.ps1"

sh.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -File """ & ps1 & """", 0, False

Set sh = Nothing
