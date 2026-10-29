$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Push-Location $root
try {
    python -m venv .audit-env
    if ($LASTEXITCODE -ne 0) { throw 'venv creation failed' }
    $python = Join-Path $root '.audit-env/Scripts/python.exe'
    & $python -m pip install 'pip-audit==2.9.0'
    if ($LASTEXITCODE -ne 0) { throw 'audit tool installation failed' }
    & $python -m pip_audit --disable-pip --no-deps -r backend/requirements.txt -f json -o validation/pip-audit.json
    if ($LASTEXITCODE -ne 0) { throw 'audit failed or vulnerabilities found; inspect validation/pip-audit.json' }
} finally { Pop-Location }
