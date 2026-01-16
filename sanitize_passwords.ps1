# Password Sanitization Script for GitHub Upload
# Run this BEFORE uploading to GitHub to replace hardcoded passwords

Write-Host "=== BGP Monitoring System - Password Sanitization ===" -ForegroundColor Cyan
Write-Host ""

# List of files to check
$files = @(
    "main.py",
    "services\feature_aggregator.py",
    "services\heuristic_detector.py",
    "services\ml_inference_service.py",
    "services\correlation_engine.py",
    "services\rpki_validator_service.py",
    "services\dashboard_api_react.py",
    "services\data_retention_service.py"
)

$totalReplaced = 0
$safePassword = "'your_password_here'"

Write-Host "Scanning Python files for hardcoded passwords..." -ForegroundColor Yellow
Write-Host ""

foreach ($file in $files) {
    if (Test-Path $file) {
        Write-Host "Checking: $file" -ForegroundColor Gray
        
        # Read file content
        $content = Get-Content $file -Raw
        
        # Count occurrences of actual password (case-sensitive)
        $passwordPattern = "'password':\s*'(?!your_password_here)[^']+'"
        $matches = [regex]::Matches($content, $passwordPattern)
        
        if ($matches.Count -gt 0) {
            Write-Host "  Found $($matches.Count) hardcoded password(s)" -ForegroundColor Red
            
            # Replace with safe placeholder
            $newContent = $content -replace $passwordPattern, "'password': 'your_password_here'"
            
            # Write back to file
            Set-Content -Path $file -Value $newContent -NoNewline
            
            Write-Host "  ✅ Replaced with placeholder" -ForegroundColor Green
            $totalReplaced += $matches.Count
        } else {
            Write-Host "  ✅ No hardcoded passwords found" -ForegroundColor Green
        }
    } else {
        Write-Host "  ⚠️  File not found: $file" -ForegroundColor Yellow
    }
    Write-Host ""
}

Write-Host "==========================================" -ForegroundColor Cyan
if ($totalReplaced -gt 0) {
    Write-Host "✅ Sanitization complete! Replaced $totalReplaced password(s)" -ForegroundColor Green
    Write-Host ""
    Write-Host "⚠️  IMPORTANT: Before using the system again, you must:" -ForegroundColor Yellow
    Write-Host "1. Restore your actual password in each file" -ForegroundColor Yellow
    Write-Host "2. Or better: Use environment variables (.env file)" -ForegroundColor Yellow
} else {
    Write-Host "✅ All files are safe! No passwords found." -ForegroundColor Green
}
Write-Host ""
Write-Host "You can now safely run: git add . && git commit" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
