# Run from repository root. Keeps existing .env values except explicitly updated integration settings.
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
function Check-Exit($label) { if ($LASTEXITCODE -ne 0) { throw "$label failed (exit $LASTEXITCODE). Stop and send the error output." } }
if (-not (Test-Path '.\platform\.env')) { Copy-Item '.\platform\.env.example' '.\platform\.env' }
$envPath = Join-Path (Get-Location) 'platform\.env'
function Set-LocalSetting($name, $value) {
    $lines = @(Get-Content -LiteralPath $envPath | Where-Object { $_ -notmatch ('^\s*'+[regex]::Escape($name)+'=') })
    $lines += "$name=$value"
    [IO.File]::WriteAllLines($envPath, $lines, (New-Object Text.UTF8Encoding($false)))
}
# The host SSH client prompts for host trust/password; neither is logged by this script.
Write-Host 'Keep an SSH tunnel running in another PowerShell window:'
Write-Host 'ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -p 10021 -L 127.0.0.1:4000:10.10.10.10:4000 team21@85.143.113.230'
Read-Host 'After establishing the tunnel, press Enter here'
Set-LocalSetting 'QWEN_BASE_URL' 'http://host.docker.internal:4000/v1'
Set-LocalSetting 'QWEN_MODEL' 'qwen3.8-27b'
Set-LocalSetting 'QWEN_API_PATH' '/chat/completions'
Set-LocalSetting 'QWEN_ALLOW_DOCKER_HOST_HTTP' 'true'
Set-LocalSetting 'QWEN_ALLOW_VM_HTTP' 'false'
Set-LocalSetting 'RWB_RUN_TIMEOUT_SECONDS' '2400'
if (-not (Get-Content $envPath | Where-Object { $_ -match '^QWEN_API_KEY=.+$' })) {
    $secureKey = Read-Host 'Qwen API key (hidden)' -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
    try { Set-LocalSetting 'QWEN_API_KEY' ([Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
}
if (-not (Get-Content $envPath | Where-Object { $_ -match '^RWB_RUNNER_TOKEN=.{32,}$' })) {
    $bytes = New-Object byte[] 32
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    Set-LocalSetting 'RWB_RUNNER_TOKEN' ([BitConverter]::ToString($bytes).Replace('-','').ToLowerInvariant())
}
docker compose --env-file .\platform\.env config --quiet
Check-Exit 'Compose config'
docker build -f infra/runner/Dockerfile.sandbox -t localhost/rwb-sandbox:dev .
Check-Exit 'Sandbox image build'
docker compose --env-file .\platform\.env up --build -d --wait api web
Check-Exit 'Platform startup'
docker compose --env-file .\platform\.env exec -T api python -m scripts.postgres_smoke
Check-Exit 'Real PostgreSQL smoke'
docker compose --env-file .\platform\.env run --rm --no-deps api python -m scripts.qwen_smoke
Check-Exit 'Real Qwen smoke'
docker compose --env-file .\platform\.env --profile pipeline up --build -d --wait
Check-Exit 'Worker and runner startup'
Write-Host 'Running REAL generation. This may take up to 45 minutes; progress is visible at localhost:4200.'
$result = docker compose --env-file .\platform\.env exec -T api python -m scripts.integration_smoke
$runExit = $LASTEXITCODE
$result | Write-Output
if ($runExit -ne 0) { throw 'Real pipeline did not pass. Send the JSON report and safe worker logs.' }
$report = $result | ConvertFrom-Json
New-Item -ItemType Directory -Force '.\verification' | Out-Null
$zip = Join-Path (Get-Location) ('verification\' + $report.runId + '.zip')
docker compose --env-file .\platform\.env cp ("api:" + $report.zipPath) $zip
Check-Exit 'ZIP download'
$product = Join-Path (Get-Location) ('verification\' + $report.runId)
Expand-Archive -LiteralPath $zip -DestinationPath $product
Write-Host "Validated ZIP extracted to $product"
Write-Host 'Next: set PRODUCT_DB_PASSWORD in the extracted .env; run product Compose and test create/list/update request in its UI. This script does not claim business acceptance.'
