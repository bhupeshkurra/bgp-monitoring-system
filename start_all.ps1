# BGP Monitoring System - Startup Script with Virtual Environment

Write-Host "Starting BGP Monitoring System..." -ForegroundColor Cyan
Write-Host ""

# Get script directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Activate venv command
$ActivateVenv = "$ScriptDir\.venv\Scripts\Activate.ps1"

# Check if venv exists
if (-not (Test-Path $ActivateVenv)) {
    Write-Host "ERROR: Virtual environment not found at .venv\" -ForegroundColor Red
    Write-Host "Please create venv first: python -m venv .venv" -ForegroundColor Yellow
    exit 1
}

Write-Host "Virtual environment found" -ForegroundColor Green
Write-Host ""

# Check and start PostgreSQL service
Write-Host "Checking PostgreSQL service..." -ForegroundColor Yellow
$pgService = Get-Service -Name postgresql-x64-16 -ErrorAction SilentlyContinue
if ($pgService) {
    if ($pgService.Status -ne 'Running') {
        Write-Host "  - PostgreSQL is stopped, starting..." -ForegroundColor Yellow
        try {
            Start-Service postgresql-x64-16
            Start-Sleep -Seconds 3
            Write-Host "  - PostgreSQL started successfully" -ForegroundColor Green
        } catch {
            Write-Host "  - ERROR: Failed to start PostgreSQL. Run as Administrator." -ForegroundColor Red
            Write-Host "  - Manual: Start-Service postgresql-x64-16" -ForegroundColor Yellow
            exit 1
        }
    } else {
        Write-Host "  - PostgreSQL is already running" -ForegroundColor Green
    }
} else {
    Write-Host "  - WARNING: PostgreSQL service not found" -ForegroundColor Yellow
}
Write-Host ""

# Start Routinator Docker Container (RPKI Validator)
Write-Host "Starting Routinator (RPKI)..." -ForegroundColor Yellow
docker start routinator | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Host "  - Routinator Docker container started" -ForegroundColor Green
} else {
    Write-Host "  - WARNING: Failed to start Routinator (RPKI features will not work)" -ForegroundColor Yellow
}
Start-Sleep -Seconds 3

Write-Host ""
Write-Host "Starting Backend Services..." -ForegroundColor Yellow

# Service 1: BGP Collector
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$ScriptDir'; & '$ActivateVenv'; Write-Host 'BGP Collector Running...' -ForegroundColor Cyan; python main.py"
Write-Host "  - BGP Collector (main.py)" -ForegroundColor Green
Start-Sleep -Seconds 2

# Service 2: Feature Aggregator
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$ScriptDir'; & '$ActivateVenv'; Write-Host 'Feature Aggregator Running...' -ForegroundColor Cyan; python services/feature_aggregator.py"
Write-Host "  - Feature Aggregator" -ForegroundColor Green
Start-Sleep -Seconds 1

# Service 3: Heuristic Detector
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$ScriptDir'; & '$ActivateVenv'; Write-Host 'Heuristic Detector Running...' -ForegroundColor Cyan; python services/heuristic_detector.py"
Write-Host "  - Heuristic Detector" -ForegroundColor Green
Start-Sleep -Seconds 1

# Service 4: ML Inference
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$ScriptDir'; & '$ActivateVenv'; Write-Host 'ML Inference Running...' -ForegroundColor Cyan; python services/ml_inference_service.py"
Write-Host "  - ML Inference Service" -ForegroundColor Green
Start-Sleep -Seconds 1

# Service 5: RPKI Validator
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$ScriptDir'; & '$ActivateVenv'; Write-Host 'RPKI Validator Running...' -ForegroundColor Cyan; python services/rpki_validator_service.py"
Write-Host "  - RPKI Validator Service" -ForegroundColor Green
Start-Sleep -Seconds 1

# Service 6: Correlation Engine
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$ScriptDir'; & '$ActivateVenv'; Write-Host 'Correlation Engine Running...' -ForegroundColor Cyan; python services/correlation_engine.py"
Write-Host "  - Correlation Engine" -ForegroundColor Green
Start-Sleep -Seconds 1

# Service 7: Data Retention (3-day rolling window)
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$ScriptDir'; & '$ActivateVenv'; Write-Host 'Data Retention Service Running (3-day window)...' -ForegroundColor Cyan; python services/data_retention_service.py"
Write-Host "  - Data Retention Service (3-day cleanup)" -ForegroundColor Green
Start-Sleep -Seconds 1

# Service 8: Dashboard API
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$ScriptDir'; & '$ActivateVenv'; Write-Host 'Dashboard API Running on port 5000...' -ForegroundColor Cyan; python services/dashboard_api_react.py"
Write-Host "  - Dashboard API (port 5000)" -ForegroundColor Green
Start-Sleep -Seconds 2

# Start Frontend
Write-Host ""
Write-Host "Starting Frontend..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$ScriptDir\frontend'; Write-Host 'React Dashboard Starting...' -ForegroundColor Cyan; npm run dev"
Write-Host "  - React Dashboard (port 3000)" -ForegroundColor Green

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "System Started Successfully!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Dashboard URL: http://localhost:3000" -ForegroundColor Yellow
Write-Host "API URL: http://localhost:5000" -ForegroundColor Yellow
Write-Host ""
Write-Host "Wait 2-3 minutes for data pipeline to initialize..." -ForegroundColor Magenta
Write-Host ""
Write-Host "To stop all services:" -ForegroundColor Red
Write-Host "  Get-Process python,node | Stop-Process -Force" -ForegroundColor Red
Write-Host "  docker stop routinator" -ForegroundColor Red
