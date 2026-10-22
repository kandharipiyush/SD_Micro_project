$ErrorActionPreference = "Continue"
Write-Host "`nBASELINE HEALTH"
curl.exe -i http://localhost:8080/health
Write-Host "`nSTOP GATEWAY A: check whether new requests are served by gateway B"
docker compose stop gateway-a
Start-Sleep -Seconds 3
curl.exe -i http://localhost:8080/health
docker compose start gateway-a
Start-Sleep -Seconds 5
Write-Host "`nSTOP REDIS: health should report degraded on selected gateway"
docker compose stop redis
Start-Sleep -Seconds 3
curl.exe -i http://localhost:8080/health
docker compose start redis
Start-Sleep -Seconds 8
Write-Host "`nFINAL HEALTH AND STATUS"
curl.exe -i http://localhost:8080/health
docker compose ps
Write-Host "Record actual results and logs; do not claim zero downtime or zero message loss without evidence."
