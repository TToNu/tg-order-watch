@echo off
:again
cd /d C:\Users\alexa\.zcode\workspace\default\tg-order-watch
python monitor.py >> monitor_run.log 2>&1
echo [%date% %time%] monitor exited (code %errorlevel%), restarting in 10s >> monitor_run.log
timeout /t 10 >nul
goto again
