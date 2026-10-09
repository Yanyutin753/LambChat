$ErrorActionPreference = 'Stop'

try {
    $root = [IO.Path]::GetFullPath($env:LAMBCHAT_INSTALL_DIR)
    $targets = @(
        (Join-Path $root 'lambchat.exe'),
        (Join-Path $root 'lambchat-daemon.exe')
    )
    # Match the installation path so other checkouts and installations stay running.
    $processes = @(Get-Process -Name lambchat,lambchat-daemon -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -and ($targets -contains [IO.Path]::GetFullPath($_.Path)) })
    foreach ($process in $processes) {
        if (-not $process.HasExited) {
            try { Stop-Process -InputObject $process -Force -ErrorAction Stop }
            catch { if (-not $process.HasExited) { throw } }
            Wait-Process -InputObject $process -Timeout 15 -ErrorAction SilentlyContinue
            if (-not $process.HasExited) { throw 'Installed process did not exit' }
        }
    }
    exit 0
} catch {
    Write-Error 'Unable to stop the installed LambChat processes'
    exit 1
}
