param(
    [Parameter(Mandatory = $true)][string]$MakeNsis,
    [string]$Hooks = ''
)
$ErrorActionPreference = 'Stop'
$root = Join-Path $env:TEMP ('lambchat-upgrade-test-' + [guid]::NewGuid())
New-Item -ItemType Directory $root | Out-Null
$owned = $null
$helper = $null
$unrelated = $null
try {
    if (-not $Hooks) { $Hooks = Join-Path $PSScriptRoot '../frontend/src-tauri/windows/hooks.nsh' }
    $Hooks = (Resolve-Path $Hooks).Path
    $legacy = @'
Unicode true
Name "Legacy upgrade fixture"
OutFile "legacy.exe"
RequestExecutionLevel user
SilentInstall silent
SilentUnInstall silent
!include "LogicLib.nsh"
Section
SetOutPath $INSTDIR
File /oname=lambchat.exe "$%WINDIR%\System32\cmd.exe"
File /oname=lambchat-daemon.exe "$%WINDIR%\System32\cmd.exe"
File /oname=locked-helper.exe "$%WINDIR%\System32\ping.exe"
FileOpen $0 "$INSTDIR\legacy.txt" w
FileWrite $0 "old"
FileClose $0
WriteUninstaller "$INSTDIR\uninstall.exe"
SectionEnd
Section Uninstall
${If} ${FileExists} "$INSTDIR\fail-uninstall"
SetErrorLevel 7
Quit
${EndIf}
Delete "$INSTDIR\lambchat.exe"
Delete "$INSTDIR\lambchat-daemon.exe"
Delete "$INSTDIR\locked-helper.exe"
Delete "$INSTDIR\legacy.txt"
Delete "$INSTDIR\uninstall.exe"
RMDir "$INSTDIR"
SectionEnd
'@
    $candidate = @'
Unicode true
Name "New upgrade fixture"
AutoCloseWindow true
OutFile "candidate.exe"
RequestExecutionLevel user
SilentInstall normal
SilentUnInstall silent
!include "LogicLib.nsh"
LangString unableToUninstall 1033 "Unable to uninstall old version"
!include "MUI2.nsh"
!include "__HOOKS__"
Var UpdateMode
Var PassiveMode
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"
Section
${IfNot} ${Silent}
${If} ${FileExists} "$INSTDIR\uninstall.exe"
${If} $UpdateMode != 1
${OrIf} $PassiveMode != 1
SetErrorLevel 8
Quit
${EndIf}
${Else}
${If} $UpdateMode == 1
${OrIf} $PassiveMode == 1
SetErrorLevel 9
Quit
${EndIf}
${EndIf}
${EndIf}
SetOutPath $INSTDIR
!insertmacro NSIS_HOOK_PREINSTALL
FileOpen $0 "$INSTDIR\new.txt" w
FileWrite $0 "new"
FileClose $0
WriteUninstaller "$INSTDIR\uninstall.exe"
SectionEnd
Section Uninstall
!insertmacro NSIS_HOOK_PREUNINSTALL
Delete "$INSTDIR\new.txt"
Delete "$INSTDIR\uninstall.exe"
RMDir "$INSTDIR"
SectionEnd
'@.Replace('__HOOKS__', $Hooks)
    Set-Content -LiteralPath (Join-Path $root 'legacy.nsi') -Value $legacy -Encoding UTF8
    Set-Content -LiteralPath (Join-Path $root 'candidate.nsi') -Value $candidate -Encoding UTF8
    foreach ($source in @('legacy.nsi', 'candidate.nsi')) {
        & $MakeNsis /V2 (Join-Path $root $source)
        if ($LASTEXITCODE -ne 0) { throw "NSIS compilation failed: $source" }
    }
    $fresh = Join-Path $root 'fresh'
    $p = Start-Process (Join-Path $root 'candidate.exe') -ArgumentList @('/P', "/D=$fresh") -Wait -PassThru
    if ($p.ExitCode -ne 0) { throw 'Fresh GUI installation incorrectly entered update mode' }
    $install = Join-Path $root 'installed'
    $data = Join-Path $root 'user-data.txt'
    Set-Content $data 'keep-me'
    $p = Start-Process (Join-Path $root 'legacy.exe') -ArgumentList @('/S', "/D=$install") -Wait -PassThru
    if ($p.ExitCode -ne 0) { throw 'Legacy fixture install failed' }
    $owned = Start-Process (Join-Path $install 'lambchat.exe') -ArgumentList '/d /c lambchat-daemon.exe /d /c locked-helper.exe 127.0.0.1 -t' -WorkingDirectory $install -WindowStyle Hidden -PassThru
    Start-Sleep -Milliseconds 500
    if ($owned.HasExited) { throw 'Locked daemon fixture exited prematurely' }
    $daemon = @(Get-CimInstance Win32_Process -Filter "ParentProcessId = $($owned.Id)" |
        Where-Object { $_.Name -eq 'lambchat-daemon.exe' })
    if ($daemon.Count -ne 1) { throw 'Expected one daemon child' }
    $child = @(Get-CimInstance Win32_Process -Filter "ParentProcessId = $($daemon[0].ProcessId)" |
        Where-Object { $_.Name -eq 'locked-helper.exe' })
    if ($child.Count -ne 1) { throw 'Expected one locked helper child' }
    $helper = Get-Process -Id $child[0].ProcessId
    $otherInstall = Join-Path $root 'other-install'
    New-Item -ItemType Directory $otherInstall | Out-Null
    Copy-Item "$env:WINDIR\System32\ping.exe" (Join-Path $otherInstall 'lambchat-daemon.exe')
    $unrelated = Start-Process (Join-Path $otherInstall 'lambchat-daemon.exe') -ArgumentList '127.0.0.1 -t' -WindowStyle Hidden -PassThru

    $p = Start-Process (Join-Path $root 'candidate.exe') -ArgumentList @('/S', "/D=$install") -Wait -PassThru
    $owned.Refresh()
    $helper.Refresh()
    if ($unrelated.HasExited) { throw 'Upgrade stopped a different installation' }
    if (-not $helper.HasExited -or (Test-Path (Join-Path $install 'locked-helper.exe'))) {
        Write-Output "Upgrade diagnostic: exit=$($p.ExitCode), daemonExited=$($owned.HasExited), helperExited=$($helper.HasExited), helperExists=$(Test-Path (Join-Path $install 'locked-helper.exe'))"
        Get-CimInstance Win32_Process -Filter "ProcessId = $($helper.Id)" | Select-Object ProcessId,ParentProcessId,ExecutablePath | Format-List | Out-String | Write-Output
        throw 'Upgrade left a child process holding an installed file'
    }
    if ($p.ExitCode -ne 0 -or -not $owned.HasExited -or (Test-Path (Join-Path $install 'legacy.txt')) -or -not (Test-Path (Join-Path $install 'new.txt'))) {
        $remaining = Get-Process -Id $owned.Id -ErrorAction SilentlyContinue
        Write-Output "Daemon observation: pid=$($owned.Id), remaining=$([bool]$remaining), name=$($remaining.ProcessName), path=$($remaining.Path)"
        throw "Silent upgrade failed: exit=$($p.ExitCode), daemonExited=$($owned.HasExited), legacyExists=$(Test-Path (Join-Path $install 'legacy.txt')), newExists=$(Test-Path (Join-Path $install 'new.txt'))"
    }
    if ((Get-Content $data) -ne 'keep-me') { throw 'User data changed' }
    # A visible/passive installer must route GUI initialization to the same cleanup.
    $p = Start-Process (Join-Path $root 'candidate.exe') -ArgumentList @('/P', "/D=$install") -Wait -PassThru
    if ($p.ExitCode -ne 0) { throw 'GUI upgrade mode was not initialized' }
    # Same-version reinstall must take the cleanup path too.
    $p = Start-Process (Join-Path $root 'candidate.exe') -ArgumentList @('/S', "/D=$install") -Wait -PassThru
    if ($p.ExitCode -ne 0 -or -not (Test-Path (Join-Path $install 'new.txt'))) { throw 'Reinstall failed' }
    $failureInstall = Join-Path $root 'failure'
    $p = Start-Process (Join-Path $root 'legacy.exe') -ArgumentList @('/S', "/D=$failureInstall") -Wait -PassThru
    if ($p.ExitCode -ne 0) { throw 'Failure fixture install failed' }
    New-Item -ItemType File (Join-Path $failureInstall 'fail-uninstall') | Out-Null
    $p = Start-Process (Join-Path $root 'candidate.exe') -ArgumentList @('/S', "/D=$failureInstall") -Wait -PassThru
    if ($p.ExitCode -eq 0 -or (Test-Path (Join-Path $failureInstall 'new.txt'))) { throw 'Failed uninstall was ignored' }
    Write-Output 'PASS: locked daemon upgrade, old files removed, data preserved, reinstall, failed uninstall aborts'
} finally {
    if ($unrelated -and -not $unrelated.HasExited) { Stop-Process -InputObject $unrelated -Force }
    if ($helper -and -not $helper.HasExited) { Stop-Process -InputObject $helper -Force }
    if ($owned -and -not $owned.HasExited) { Stop-Process -InputObject $owned -Force }
    Remove-Item -LiteralPath $root -Recurse -Force
}
