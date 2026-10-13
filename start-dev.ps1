param([int]$ApiPort = 8000, [int]$FrontendPort = 5173, [switch]$Preview)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$backendRoot = Join-Path $projectRoot 'backend'
$frontendRoot = Join-Path $projectRoot 'frontend'
$runtimeRoot = Join-Path $projectRoot '.audit/implementation/runtime'
$pythonPath = Join-Path $backendRoot '.venv-win/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Install backend dependencies in .venv-win first; see README.md.' }
if (-not (Test-Path -LiteralPath (Join-Path $frontendRoot 'node_modules/vite/bin/vite.js'))) { throw 'Run npm.cmd ci in frontend first.' }
foreach ($port in @($ApiPort, $FrontendPort)) {
    # netstat works on machines where Get-NetTCPConnection cannot query CIM.
    if (netstat -ano | Select-String -Pattern (':'+$port+'\s+.*LISTENING')) { throw "Port $port is occupied. Stop the existing DevReason service first." }
}
New-Item -ItemType Directory -Force -Path $runtimeRoot | Out-Null
Push-Location $projectRoot
try { docker compose -f compose.dev.yml -p devreason-dev up -d redis; if ($LASTEXITCODE -ne 0) { throw 'Docker Redis could not start.' } } finally { Pop-Location }
$env:REDIS_URL = 'redis://127.0.0.1:6381/0'
$env:PORT = [string]$ApiPort
$env:FRONTEND_BASE_URL = "http://localhost:$FrontendPort"
$env:GITHUB_OAUTH_CALLBACK_URL = "http://localhost:$ApiPort/api/auth/github/callback"
$env:API_BASE_URL = "http://localhost:$ApiPort"
$env:ALLOWED_ORIGINS = "http://localhost:$FrontendPort,http://127.0.0.1:$FrontendPort"
$env:VITE_API_URL = "http://localhost:$ApiPort"
$env:BRANCH_REVIEWS_ENABLED = 'true'
if ($Preview) {
    Push-Location $frontendRoot
    try { npm.cmd run build; if ($LASTEXITCODE -ne 0) { throw 'Frontend production build failed.' } } finally { Pop-Location }
}
Push-Location $backendRoot
try { & $pythonPath -m alembic upgrade head; if ($LASTEXITCODE -ne 0) { throw 'Database migrations failed.' } } finally { Pop-Location }
$api = Start-Process -FilePath $pythonPath -ArgumentList '-m','src.run' -WorkingDirectory $backendRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtimeRoot 'api.log') -RedirectStandardError (Join-Path $runtimeRoot 'api.error.log') -PassThru
$worker = Start-Process -FilePath $pythonPath -ArgumentList '-m','src.worker' -WorkingDirectory $backendRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtimeRoot 'worker.log') -RedirectStandardError (Join-Path $runtimeRoot 'worker.error.log') -PassThru
$nodePath = (Get-Command node).Source
$frontendArguments = @('node_modules/vite/bin/vite.js')
if ($Preview) { $frontendArguments += 'preview' }
$frontendArguments += @('--host','localhost','--port',([string]$FrontendPort),'--strictPort')
$frontend = Start-Process -FilePath $nodePath -ArgumentList $frontendArguments -WorkingDirectory $frontendRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtimeRoot 'frontend.log') -RedirectStandardError (Join-Path $runtimeRoot 'frontend.error.log') -PassThru
@{api = $api.Id; worker = $worker.Id; frontend = $frontend.Id; apiPort = $ApiPort; frontendPort = $FrontendPort; frontendMode = $(if ($Preview) {'preview'} else {'development'}); startedAt = @{api = $api.StartTime.ToUniversalTime().Ticks; worker = $worker.StartTime.ToUniversalTime().Ticks; frontend = $frontend.StartTime.ToUniversalTime().Ticks}} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runtimeRoot 'processes.json')
Write-Output "Frontend: http://localhost:$FrontendPort"
Write-Output "API: http://localhost:$ApiPort/docs"
Write-Output "Readiness: http://localhost:$ApiPort/api/ready"
Write-Output "GitHub App callback must match http://localhost:$ApiPort/api/auth/github/callback"
