$ErrorActionPreference = "Continue"
Set-Location "C:\Users\alexa\.zcode\workspace\default\tg-order-watch"

$lists = @{
  "m1.csv" = "https://raw.githubusercontent.com/SoliSpirit/mtproto/master/all_proxies.csv"
  "m2.json" = "https://raw.githubusercontent.com/MrMoja/mtprotoproxy/main/proxies.json"
  "m3.txt" = "https://raw.githubusercontent.com/ALIILAPRO/MTProtoProxy/main/proxy.txt"
}
foreach ($name in $lists.Keys) {
  try {
    Invoke-WebRequest -Uri $lists[$name] -OutFile $name -TimeoutSec 25
    $item = Get-Item $name
    if ($item.Length -gt 20) {
      Write-Host ("--- " + $name + " (" + $item.Length + " bytes)")
      Get-Content $name -TotalCount 4
    }
  } catch { Write-Host ($name + ": " + $_.Exception.Message) }
}
