$ErrorActionPreference = "Continue"
Set-Location "C:\Users\alexa\.zcode\workspace\default\tg-order-watch"
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/dubblebyte/free-mtproto-proxies/main/proxies.json" -OutFile "mtproto.json" -TimeoutSec 30
$item = Get-Item mtproto.json
Write-Host ("size: " + $item.Length)
Get-Content mtproto.json -TotalCount 1
