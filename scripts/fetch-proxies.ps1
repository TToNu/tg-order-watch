$ErrorActionPreference = "Continue"
Set-Location "C:\Users\alexa\.zcode\workspace\default\tg-order-watch"

Invoke-WebRequest -Uri "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt" -OutFile "socks5.txt" -TimeoutSec 30
try {
  Invoke-WebRequest -Uri "https://raw.githubusercontent.com/SoliSpirit/mtproto/main/all_proxies.csv" -OutFile "mtproto.csv" -TimeoutSec 30
} catch { Write-Host "mtproto list unavailable: $_" }

Write-Host ("socks5: " + (Get-Content socks5.txt | Measure-Object -Line).Lines + " lines")
if (Test-Path mtproto.csv) { Write-Host ("mtproto: " + (Get-Content mtproto.csv | Measure-Object -Line).Lines + " lines") }
Write-Host "--- socks5 sample ---"
Get-Content socks5.txt -TotalCount 5
if (Test-Path mtproto.csv) { Write-Host "--- mtproto sample ---"; Get-Content mtproto.csv -TotalCount 3 }
