$ErrorActionPreference = "Stop"

$env:OPENBLAS_NUM_THREADS = "1"
$env:OMP_NUM_THREADS = "1"
$env:MKL_NUM_THREADS = "1"
$env:NUMEXPR_NUM_THREADS = "1"

if (Get-Command uv -ErrorAction SilentlyContinue) {
    uv run python -m src.mcp_servers.remote_vector_server
    exit $LASTEXITCODE
}

$venvPython = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
if (Test-Path -LiteralPath $venvPython) {
    & $venvPython -m src.mcp_servers.remote_vector_server
    exit $LASTEXITCODE
}

python -m src.mcp_servers.remote_vector_server
exit $LASTEXITCODE
