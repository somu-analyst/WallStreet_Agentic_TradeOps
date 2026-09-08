@echo off
rem Weekly offsite backup -> Google Drive desktop sync folder (no OAuth needed).
rem Capture-forward parquet chains are UNREBUILDABLE; DB copied too (newer-only).
rem Runs via Task Scheduler "NYSE_OffsiteBackup" (Sun 12:00, catches up if missed).

set SRC=C:\Users\srini\Options_chain_data
set DST=G:\My Drive\NYSE_backup

robocopy "%SRC%\openbb_chains" "%DST%\openbb_chains" *.parquet /XO /NP /R:2 /W:5
robocopy "%SRC%" "%DST%" US_data_OpenBB.db /XO /NP /R:2 /W:5

echo [%date% %time%] backup done >> "%SRC%\NYSE_DATA\logs\backup_offsite.log"
