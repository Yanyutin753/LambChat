param(
    [Parameter(Mandatory = $true)][string]$Verifier,
    [Parameter(Mandatory = $true)][string]$Artifact,
    [Parameter(Mandatory = $true)][string]$Version
)
$ErrorActionPreference = 'Stop'
if ($env:GITHUB_ACTIONS -ne 'true') { throw 'Run this installation regression only on an isolated GitHub Actions runner' }
$Verifier = (Resolve-Path $Verifier).Path
$Artifact = (Resolve-Path $Artifact).Path
$Signature = "$Artifact.sig"
$root = Join-Path $env:TEMP ('lambchat-native-update-' + [guid]::NewGuid())
New-Item -ItemType Directory $root | Out-Null
$markers = @(
    (Join-Path $env:APPDATA ('com.lambchat.app\updater-smoke-' + [guid]::NewGuid() + '.txt')),
    (Join-Path $env:LOCALAPPDATA ('com.lambchat.app\updater-smoke-' + [guid]::NewGuid() + '.txt'))
)
try {
    & $Verifier $Artifact $Signature $Version
    if ($LASTEXITCODE -ne 0) { throw 'Candidate native signature verification failed' }
    # Tauri patches the NSIS bundle marker, then restores the portable executable.
    $unpacked = Join-Path $root 'expected'
    & 7z x $Artifact "-o$unpacked" lambchat.exe -r -y
    if ($LASTEXITCODE -ne 0) { throw 'Cannot extract the verified installer executable' }
    $expected = @(Get-ChildItem $unpacked -Recurse -Filter lambchat.exe)
    if ($expected.Count -ne 1) { throw 'Expected exactly one packaged application executable' }
    $expectedHash = (Get-FileHash $expected[0].FullName -Algorithm SHA256).Hash
    foreach ($marker in $markers) {
        New-Item -ItemType Directory -Force (Split-Path $marker) | Out-Null
        Set-Content $marker 'keep-me'
    }
    foreach ($baseline in @('v2.15.2', 'v2.15.3-dev.1')) {
        $download = Join-Path $root $baseline
        New-Item -ItemType Directory $download | Out-Null
        $name = "LambChat-$baseline-Windows-x64-setup.exe"
        & gh release download $baseline --repo $env:GITHUB_REPOSITORY --pattern $name --pattern '*_x64-setup.exe.sig' --dir $download
        if ($LASTEXITCODE -ne 0) { throw "Baseline download failed: $baseline" }
        $legacy = Join-Path $download $name
        $legacySig = @(Get-ChildItem $download -Filter '*_x64-setup.exe.sig')
        if ($legacySig.Count -ne 1) { throw 'Ambiguous baseline signature' }
        $core = ($baseline.TrimStart('v') -split '-dev\.')[0]
        & $Verifier $legacy ($legacySig[0].FullName) $core
        if ($LASTEXITCODE -ne 0) { throw 'Baseline native signature verification failed' }
        $install = Join-Path $download 'installed'
        $process = Start-Process $legacy -ArgumentList @('/S', "/D=$install") -Wait -PassThru
        if ($process.ExitCode -ne 0) { throw 'Baseline installation failed' }
        $exe = Join-Path $install 'lambchat.exe'
        if (-not (Test-Path $exe)) { throw 'Baseline executable missing' }
        if ((Get-FileHash $exe -Algorithm SHA256).Hash -eq $expectedHash) { throw 'Baseline unexpectedly equals candidate' }
        & $Verifier $Artifact $Signature $Version ($baseline.TrimStart('v')) $exe
        if ($LASTEXITCODE -ne 0) { throw 'Native updater failed to start installation' }
        $deadline = (Get-Date).AddSeconds(240)
        $installed = $false
        do {
            Start-Sleep -Seconds 1
            $installers = @(Get-Process -Name "test-$Version-installer*" -ErrorAction SilentlyContinue)
            if ($installers.Count -eq 0 -and (Test-Path $exe) -and (Test-Path (Join-Path $install 'uninstall.exe'))) {
                try { $installed = (Get-FileHash $exe -Algorithm SHA256).Hash -eq $expectedHash } catch { $installed = $false }
            }
        } until ($installed -or (Get-Date) -ge $deadline)
        if (-not $installed) {
            Write-Output "Expected executable SHA256: $expectedHash"
            if (Test-Path $exe) { Get-FileHash $exe -Algorithm SHA256 | Format-List | Out-String | Write-Output }
            Get-ChildItem $install -ErrorAction SilentlyContinue | Select-Object Name,Length | Format-Table | Out-String | Write-Output
            Get-CimInstance Win32_Process | Where-Object {
                $_.Name -match 'installer|uninstall|powershell|lambchat' -or $_.ExecutablePath -like "$root*"
            } | Select-Object ProcessId,ParentProcessId,Name,ExecutablePath,CommandLine | Format-List | Out-String | Write-Output
            Get-Process | Where-Object { $_.MainWindowTitle } |
                Select-Object Id,ProcessName,MainWindowTitle | Format-Table | Out-String | Write-Output
            throw "Native installation did not complete: $baseline -> $Version"
        }
        foreach ($marker in $markers) {
            if ((Get-Content $marker) -ne 'keep-me') { throw 'User data changed' }
        }
        $daemon = Join-Path $install 'lambchat-daemon.exe'
        $actual = (& $daemon version | Select-Object -Last 1).Trim()
        if ($LASTEXITCODE -ne 0 -or $actual -ne ($Version -split '-dev\.')[0]) { throw 'Updated daemon cannot run' }
        Write-Output "PASS: native updater $baseline -> $Version, installed executable hash matches, data preserved, daemon runs"
        $uninstall = Start-Process (Join-Path $install 'uninstall.exe') -ArgumentList '/S' -Wait -PassThru
        if ($uninstall.ExitCode -ne 0) { throw 'Test installation cleanup failed' }
    }
} finally {
    Get-Process -Name "test-$Version-installer*" -ErrorAction SilentlyContinue | Stop-Process -Force
    foreach ($marker in $markers) { Remove-Item -LiteralPath $marker -Force -ErrorAction SilentlyContinue }
    Remove-Item -LiteralPath $root -Recurse -Force
}
