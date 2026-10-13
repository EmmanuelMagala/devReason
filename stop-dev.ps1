$ErrorActionPreference = 'Stop'
$runtimeFile = Join-Path $PSScriptRoot '.audit/implementation/runtime/processes.json'
if (-not (Test-Path -LiteralPath $runtimeFile)) { Write-Output 'No managed development processes found.'; return }
$runtime = Get-Content -LiteralPath $runtimeFile -Raw | ConvertFrom-Json
foreach ($name in @('api','worker','frontend')) {
    $processId = $runtime.$name
    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if (-not $process) { continue }
    $expectedPath = if ($name -eq 'frontend') { (Get-Command node).Source } else { [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'backend/.venv-win/Scripts/python.exe')) }
    if ($process.Path -ne $expectedPath) { throw "Process $processId no longer matches this project's managed executable." }
    if ($runtime.startedAt -and $process.StartTime.ToUniversalTime().Ticks -ne $runtime.startedAt.$name) { throw "Process $processId has been reused; refusing to stop it." }
    & "$env:SystemRoot/System32/taskkill.exe" /PID $processId /T /F | Out-Null
}
Write-Output 'Managed API, worker, and frontend stopped. Local Redis data remains available.'
