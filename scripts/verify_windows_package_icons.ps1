param(
    [Parameter(Mandatory = $true)][string]$Setup,
    [Parameter(Mandatory = $true)][string]$App,
    [string]$Icon = 'frontend/src-tauri/icons/icon.ico'
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$reference = [System.Drawing.Icon]::new((Resolve-Path $Icon).Path, 32, 32)
$expected = $reference.ToBitmap()
function Assert-BrandIcon([string]$Path) {
    $actualIcon = [System.Drawing.Icon]::ExtractAssociatedIcon((Resolve-Path $Path).Path)
    if ($null -eq $actualIcon) { throw "Missing icon: $Path" }
    $actual = $actualIcon.ToBitmap()
    try {
        if ($actual.Size -ne $expected.Size) { throw "Wrong icon dimensions: $Path" }
        for ($y = 0; $y -lt $expected.Height; $y++) {
            for ($x = 0; $x -lt $expected.Width; $x++) {
                $a = $actual.GetPixel($x, $y)
                $e = $expected.GetPixel($x, $y)
                if ($a.A -ne $e.A -or ($e.A -ne 0 -and $a.ToArgb() -ne $e.ToArgb())) {
                    throw "Non-LambChat icon: $Path"
                }
            }
        }
    } finally { $actual.Dispose(); $actualIcon.Dispose() }
}
$install = Join-Path $env:TEMP ('lambchat-icon-test-' + [guid]::NewGuid())
try {
    Assert-BrandIcon $Setup
    Assert-BrandIcon $App
    $process = Start-Process $Setup -ArgumentList @('/S', "/D=$install") -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw "Icon smoke installation failed: $($process.ExitCode)" }
    Assert-BrandIcon (Join-Path $install 'lambchat.exe')
    Assert-BrandIcon (Join-Path $install 'uninstall.exe')
    Write-Host 'PASS LambChat icons in setup, application, installed application and uninstaller'
} finally {
    $uninstaller = Join-Path $install 'uninstall.exe'
    if (Test-Path $uninstaller) {
        $process = Start-Process $uninstaller -ArgumentList @('/S', "_?=$install") -Wait -PassThru
        if ($process.ExitCode -ne 0) { throw "Icon smoke uninstall failed: $($process.ExitCode)" }
    }
    if (Test-Path $install) { Remove-Item -Recurse -Force $install }
    $expected.Dispose(); $reference.Dispose()
}
