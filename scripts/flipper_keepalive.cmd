@echo off
:again
cd /d C:\Users\alexa\.zcode\workspace\default\tg-order-watch
python scripts\lzt_flip_loop.py >> flip_run.log 2>&1
echo [%date% %time%] flipper exited (code %errorlevel%), restarting in 10s >> flip_run.log
timeout /t 10 >nul
goto again
