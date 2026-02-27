@echo off
cd /d "C:\Users\trist\Repos\Portfolio Agent"

echo Running weekly audit...
".venv\Scripts\python.exe" weekly_audit.py

echo.
echo Done.
pause