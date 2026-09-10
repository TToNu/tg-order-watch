@echo off
cd /d C:\Users\alexa\.zcode\workspace\default\tg-order-watch
:again
python scripts\lzt_flip_loop.py >> flip_run.log 2>&1
if %errorlevel% equ 0 goto :eof
echo [%date% %time%] flipper exited (code %errorlevel%), restart in 10s >> flip_run.log
timeout /t 10 >nul
goto again
