@echo off
cd /d C:\Users\alexa\.zcode\workspace\default\tg-order-watch
:again
python monitor.py >> monitor_run.log 2>&1
if %errorlevel% equ 0 goto :eof
echo [%date% %time%] monitor exited (code %errorlevel%), restart in 10s >> monitor_run.log
timeout /t 10 >nul
goto again
