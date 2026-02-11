# Noctem Research Agent Launcher
# PowerShell script to start the research agent with proper error handling

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "🌙 Noctem Research Agent Launcher" -ForegroundColor Cyan
Write-Host "=" * 50
Write-Host ""

# Get script directory
$RESEARCH_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RESEARCH_DIR

# Check Python
Write-Host "Checking prerequisites..." -ForegroundColor Yellow
Write-Host ""

try {
    $pythonVersion = python --version 2>&1
    Write-Host "✓ Python: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ Python not found!" -ForegroundColor Red
    Write-Host "   Install Python 3.8+ from: https://www.python.org/"
    exit 1
}

# Check Warp CLI
try {
    $warpCheck = warp --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ Warp CLI: Available" -ForegroundColor Green
    } else {
        throw "Warp CLI check failed"
    }
} catch {
    Write-Host "❌ Warp CLI not found or not authenticated!" -ForegroundColor Red
    Write-Host "   1. Download from: https://www.warp.dev/" -ForegroundColor Yellow
    Write-Host "   2. Install and authenticate: warp login" -ForegroundColor Yellow
    Write-Host ""
    $continue = Read-Host "Continue anyway? (y/N)"
    if ($continue -ne "y") {
        exit 1
    }
}

Write-Host ""
Write-Host "Starting research agent..." -ForegroundColor Green
Write-Host "Press Ctrl+C to stop (state will be saved)" -ForegroundColor Yellow
Write-Host ""
Write-Host "=" * 50
Write-Host ""

# Run the research agent
try {
    python research_agent.py
} catch {
    Write-Host ""
    Write-Host "❌ Research agent stopped with error:" -ForegroundColor Red
    Write-Host $_.Exception.Message
    exit 1
}

Write-Host ""
Write-Host "Research agent finished." -ForegroundColor Green
