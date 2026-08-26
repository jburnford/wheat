@echo off
rem Township General Register entry app — double-click to start.
rem Finds the register images on Q: or G: (or \\datastore\HGISLab); pass a path to override.
cd /d "%~dp0..\.."
python tools\register_entry\app.py %*
pause
