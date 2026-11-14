$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    Write-Host 'Create the environment first: python -m venv .venv'
    Write-Host 'Then install: .venv/Scripts/python.exe -m pip install -r requirements.txt'
    exit 1
}
Write-Host 'KAIJU LAB: http://127.0.0.1:8000'
& $taskPython -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
