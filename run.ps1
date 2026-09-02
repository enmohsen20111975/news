# Install and run the local news agent on Windows.
[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$AgentArguments
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

$Python = Get-Command py -ErrorAction SilentlyContinue
if (-not $Python) {
    $Python = Get-Command python -ErrorAction SilentlyContinue
}
if (-not $Python) {
    throw 'Python 3 is not installed or is not available on PATH.'
}

$VenvPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $VenvPython)) {
    Write-Host 'Creating the Windows Python virtual environment...'
    if ($Python.Name -eq 'py.exe') {
        & $Python.Source -3 -m venv (Join-Path $ProjectRoot '.venv')
    } else {
        & $Python.Source -m venv (Join-Path $ProjectRoot '.venv')
    }
}

Write-Host 'Installing project dependencies...'
& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -r (Join-Path $ProjectRoot 'requirements.txt')

if (-not (Test-Path (Join-Path $ProjectRoot '.env'))) {
    Copy-Item (Join-Path $ProjectRoot '.env.example') (Join-Path $ProjectRoot '.env')
    Write-Warning 'Created .env from the template. Configure it and run again.'
    exit 1
}

try {
    Invoke-RestMethod -Uri 'http://localhost:11434/api/tags' -TimeoutSec 3 | Out-Null
} catch {
    Write-Warning 'Ollama is not responding. Start Ollama and run again.'
    exit 1
}

Write-Host 'Starting News Agent...'
$MainScript = Join-Path $ProjectRoot 'main.py'
& $VenvPython $MainScript $AgentArguments
exit $LASTEXITCODE
