<#
.SYNOPSIS
    One-shot launcher for SwarmIQ local development.

.DESCRIPTION
    Verifies prerequisites, builds and starts the docker-compose stack
    (app + Redis), waits for /health, and opens the app in the default
    browser.

.PARAMETER NoBrowser
    Skip auto-opening the browser.

.PARAMETER Rebuild
    Force `--no-cache` rebuild of the app image (use after dependency changes).

.PARAMETER Down
    Stop and remove the compose stack instead of starting it.

.PARAMETER Logs
    Tail compose logs after startup instead of detaching.

.EXAMPLE
    .\dev.ps1
    Standard run: build (if needed), start, open browser.

.EXAMPLE
    .\dev.ps1 -Rebuild
    Rebuild from scratch — use after editing requirements.txt or Dockerfile.

.EXAMPLE
    .\dev.ps1 -Down
    Tear down the stack.

.EXAMPLE
    .\dev.ps1 -Logs
    Start the stack and stream combined logs.
#>

[CmdletBinding()]
param(
    [switch]$NoBrowser,
    [switch]$Rebuild,
    [switch]$Down,
    [switch]$Logs
)

$ErrorActionPreference = "Stop"
$ScriptRoot = $PSScriptRoot
$Url        = "http://localhost:8000"
$HealthUrl  = "$Url/health"

function Write-Step($msg)    { Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)      { Write-Host "    $msg" -ForegroundColor Green }
function Write-WarnLine($msg){ Write-Host "    $msg" -ForegroundColor Yellow }
function Write-Fail($msg)    { Write-Host "    $msg" -ForegroundColor Red }

# ── Preflight ─────────────────────────────────────────────────────────────────
Write-Step "Preflight checks"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Fail "Docker CLI not found. Install Docker Desktop and retry."
    exit 1
}

try { docker info 2>$null | Out-Null }
catch {
    Write-Fail "Docker daemon is not running. Start Docker Desktop and retry."
    exit 1
}
Write-Ok "Docker daemon: reachable."

$composeCmd = $null
docker compose version 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) { $composeCmd = @("docker", "compose") }
else {
    if (Get-Command docker-compose -ErrorAction SilentlyContinue) {
        $composeCmd = @("docker-compose")
    } else {
        Write-Fail "Neither 'docker compose' nor 'docker-compose' is available."
        exit 1
    }
}
Write-Ok ("Compose backend: " + ($composeCmd -join " "))

$envPath = Join-Path $ScriptRoot ".env"
if (-not (Test-Path $envPath)) {
    Write-WarnLine ".env not found — copying from .env.example."
    $examplePath = Join-Path $ScriptRoot ".env.example"
    if (-not (Test-Path $examplePath)) {
        Write-Fail ".env.example missing — cannot bootstrap."
        exit 1
    }
    Copy-Item $examplePath $envPath
    Write-WarnLine "Edit .env and fill in real Azure OpenAI + Tavily keys, then re-run this script."
    exit 1
}

$envText = Get-Content $envPath -Raw
$placeholders = @()
foreach ($needle in @(
    "your_azure_openai_api_key_here",
    "your_tavily_key_here",
    "your-resource-name.openai.azure.com",
    "your_deployment_name_here"
)) {
    if ($envText -match [regex]::Escape($needle)) { $placeholders += $needle }
}
if ($placeholders.Count -gt 0) {
    Write-WarnLine ".env still contains placeholders:"
    $placeholders | ForEach-Object { Write-Host "      - $_" -ForegroundColor Yellow }
    Write-WarnLine "Agents will fail until you fill these in."
}

# ── Down ──────────────────────────────────────────────────────────────────────
if ($Down) {
    Write-Step "Stopping compose stack"
    & $composeCmd[0] @($composeCmd[1..($composeCmd.Length - 1)] + @("down")) -ErrorAction Continue
    Write-Ok "Stack down."
    exit 0
}

# ── Build + Up ────────────────────────────────────────────────────────────────
Write-Step "Starting compose stack"
$composeArgs = @("up", "-d", "--build")
if ($Rebuild) { $composeArgs += "--force-recreate"; $composeArgs += "--no-deps" }

& $composeCmd[0] @($composeCmd[1..($composeCmd.Length - 1)] + $composeArgs)
if ($LASTEXITCODE -ne 0) {
    Write-Fail "Compose failed. See logs above."
    exit 1
}
Write-Ok "Containers started."

# ── Health wait ───────────────────────────────────────────────────────────────
Write-Step "Waiting for /health (timeout 90 s)"
$deadline = (Get-Date).AddSeconds(90)
$ready = $false
while ((Get-Date) -lt $deadline) {
    try {
        $resp = Invoke-WebRequest -Uri $HealthUrl -TimeoutSec 3 -UseBasicParsing -ErrorAction Stop
        if ($resp.StatusCode -eq 200) { $ready = $true; break }
    } catch { Start-Sleep -Milliseconds 800 }
}

if (-not $ready) {
    Write-Fail "Service did not become healthy in 90 s. Tail logs with: .\dev.ps1 -Logs"
    exit 1
}
Write-Ok "/health responding."

# ── Browser ───────────────────────────────────────────────────────────────────
if (-not $NoBrowser) {
    Write-Step "Opening browser"
    Start-Process $Url
}

Write-Host ""
Write-Host "SwarmIQ is up." -ForegroundColor Green
Write-Host "  App:    $Url"
Write-Host "  Health: $HealthUrl"
Write-Host "  Stop:   .\dev.ps1 -Down"
Write-Host "  Logs:   .\dev.ps1 -Logs"
Write-Host ""

# ── Optional log tail ────────────────────────────────────────────────────────
if ($Logs) {
    Write-Step "Tailing logs (Ctrl-C to detach; stack keeps running)"
    & $composeCmd[0] @($composeCmd[1..($composeCmd.Length - 1)] + @("logs", "-f"))
}
