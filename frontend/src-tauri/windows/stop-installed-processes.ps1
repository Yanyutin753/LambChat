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
            # Descendants can keep bundled DLLs/executables locked after the parent exits.
            try { & "$env:WINDIR\System32\taskkill.exe" /PID $process.Id /T /F | Out-Null }
            catch { if (-not $process.HasExited) { throw } }
            if ($LASTEXITCODE -ne 0 -and -not $process.HasExited) {
                throw 'Installed process tree did not stop'
            }
            Wait-Process -InputObject $process -Timeout 15 -ErrorAction SilentlyContinue
            if (-not $process.HasExited) { throw 'Installed process did not exit' }
        }
    }
    exit 0
} catch {
    Write-Error "Unable to stop the installed LambChat processes: $($_.Exception.Message)"
    exit 1
}
