[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$Port = 8501
$LanAddress = "0.0.0.0"
$RepoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$App = Join-Path $RepoRoot "app\main.py"

if (-not (Test-Path -LiteralPath (Join-Path $RepoRoot ".git"))) {
    throw "Repository root is invalid: $RepoRoot"
}
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Python .venv was not found at: $Python"
}
if (-not (Test-Path -LiteralPath $App -PathType Leaf)) {
    throw "Streamlit entry point was not found at: $App"
}

$Listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
if ($null -ne $Listener) {
    $Owners = ($Listener | Select-Object -ExpandProperty OwningProcess -Unique) -join ", "
    throw "TCP port $Port already has a listener (PID: $Owners). Stop the known process or choose the localhost workflow; no process was terminated."
}

Write-Host "Rohlik Decision Hub - LAN mode"
Write-Host "Repository: $RepoRoot"
Write-Host "One foreground Streamlit process will listen on ${LanAddress}:$Port."
Write-Host "Find the host IPv4 address with:"
Write-Host "  Get-NetIPAddress -AddressFamily IPv4 | Where-Object { `$_.IPAddress -notlike '127.*' -and `$_.IPAddress -notlike '169.254.*' } | Format-Table InterfaceAlias,IPAddress"
Write-Host "On a client in the same trusted LAN, open: http://<HOST_IPV4>:$Port"
Write-Warning "This is unencrypted HTTP. Use test accounts and test data only; do not expose this port to the Internet."
Write-Host "Press Ctrl+C in this window to stop the server."

$PreviousNetworkMode = $env:RDH_NETWORK_MODE
Push-Location $RepoRoot
try {
    $env:RDH_NETWORK_MODE = "LAN"
    & $Python -m streamlit run $App --server.address $LanAddress --server.port $Port
    if ($LASTEXITCODE -ne 0) {
        throw "Streamlit exited with code $LASTEXITCODE."
    }
}
finally {
    if ($null -eq $PreviousNetworkMode) {
        Remove-Item Env:RDH_NETWORK_MODE -ErrorAction SilentlyContinue
    }
    else {
        $env:RDH_NETWORK_MODE = $PreviousNetworkMode
    }
    Pop-Location
}
