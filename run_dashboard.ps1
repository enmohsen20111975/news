# Run the News Agent dashboard on Windows.
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

$VenvPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $VenvPython)) {
    throw 'The .venv environment is missing. Run .\run.ps1 first.'
}

& $VenvPython -m uvicorn ui.dashboard:app --host 0.0.0.0 --port 8001
exit $LASTEXITCODE
