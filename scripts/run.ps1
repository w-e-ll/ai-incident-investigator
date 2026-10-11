param([ValidateSet('Setup','Api','Ui','Test','DockerUp','DockerVerify','DockerStatus','DockerDown','ObservabilityUp')][string]$Action = 'Setup')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path $PSScriptRoot -Parent)
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    $uvFallback = Join-Path $env:USERPROFILE '.local/bin/uv.exe'
    if (Test-Path -LiteralPath $uvFallback) { Set-Alias -Name uv -Value $uvFallback }
}
function Invoke-Compose {
    $composeFallback = 'C:/Program Files/Docker/Docker/resources/cli-plugins/docker-compose.exe'
    if (Test-Path -LiteralPath $composeFallback) {
        & $composeFallback @args
    } else {
        docker compose @args
    }
}
switch ($Action) {
    'Setup' {
        uv sync --frozen
        if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
        uv run python scripts/setup_env.py
    }
    'Api' { uv run uvicorn api.main:app --host 127.0.0.1 --port 8000 }
    'Ui' { uv run streamlit run streamlit_app.py --server.address 127.0.0.1 --server.port 8501 }
    'Test' {
        uv run ruff check .
        if ($LASTEXITCODE -ne 0) { throw 'Ruff failed' }
        uv run pytest -q
    }
    'DockerUp' {
        Invoke-Compose up --build --wait --wait-timeout 180
        if ($LASTEXITCODE -ne 0) {
            Invoke-Compose ps -a
            Invoke-Compose logs --tail 60 migrate api ui
            throw 'Application startup failed. Review the service status and logs above.'
        }
        Write-Host 'Application is ready: http://127.0.0.1:8501'
    }
    'DockerVerify' {
        Invoke-Compose --profile tests build
        if ($LASTEXITCODE -ne 0) { throw 'Docker build failed' }
        Invoke-Compose up -d db migrate
        if ($LASTEXITCODE -ne 0) { throw 'Database or migration startup failed' }
        Invoke-Compose --profile tests run --rm tests
        if ($LASTEXITCODE -ne 0) { throw 'Container verification failed' }
        Write-Host 'Verification completed. To start API and UI, run: ./scripts/run.ps1 DockerUp'
    }
    'ObservabilityUp' {
        Invoke-Compose -f compose.yaml -f compose.observability.yaml --profile observability up -d --build api worker otel-collector prometheus tempo grafana
        if ($LASTEXITCODE -ne 0) { throw 'Observability startup failed' }
        Write-Host 'Grafana: http://127.0.0.1:3000 | Prometheus: http://127.0.0.1:9090'
    }
    'DockerStatus' {
        Invoke-Compose ps -a
        if ($LASTEXITCODE -ne 0) { throw 'Cannot read Docker service status' }
        Invoke-Compose logs --tail 60 migrate api ui
    }
    'DockerDown' { Invoke-Compose down }
}
if ($LASTEXITCODE -ne 0) { throw "$Action failed" }
