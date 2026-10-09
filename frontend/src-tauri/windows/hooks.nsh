!define LAMBCHAT_HOOK_DIR "${__FILEDIR__}"

; Tauri CLI 2.11.2 declares UpdateMode after including hooks, so defer this
; function until Modern UI expands it. Keep both standard GUI callbacks.
!macroundef MUI_FUNCTION_GUIINIT
!macro MUI_FUNCTION_GUIINIT
  Function .onGUIInit
    !insertmacro MUI_GUIINIT_OUTERDIALOG ""
    !ifdef MUI_PAGE_FUNCTION_GUIINIT
      Call "${MUI_PAGE_FUNCTION_GUIINIT}"
    !endif
    !ifdef MUI_CUSTOMFUNCTION_GUIINIT
      Call "${MUI_CUSTOMFUNCTION_GUIINIT}"
    !endif
    ; Skip the earlier legacy-uninstaller page; PREINSTALL owns safe cleanup.
    ${If} ${FileExists} "$INSTDIR\uninstall.exe"
      StrCpy $UpdateMode 1
      StrCpy $PassiveMode 1
    ${EndIf}
  FunctionEnd
!macroend

!macro StopInstalledLambChat
  InitPluginsDir
  File /oname=$PLUGINSDIR\stop-installed-processes.ps1 "${LAMBCHAT_HOOK_DIR}\stop-installed-processes.ps1"
  System::Call 'kernel32::SetEnvironmentVariableW(w "LAMBCHAT_INSTALL_DIR", w "$INSTDIR")'
  StrCpy $2 "$SYSDIR\WindowsPowerShell\v1.0\powershell.exe"
  ${If} ${FileExists} "$WINDIR\Sysnative\WindowsPowerShell\v1.0\powershell.exe"
    StrCpy $2 "$WINDIR\Sysnative\WindowsPowerShell\v1.0\powershell.exe"
  ${EndIf}
  nsExec::ExecToStack /TIMEOUT=45000 '"$2" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$PLUGINSDIR\stop-installed-processes.ps1"'
  Pop $0
  Pop $1
  System::Call 'kernel32::SetEnvironmentVariableW(w "LAMBCHAT_INSTALL_DIR", p 0)'
  ${If} $0 != 0
    SetErrorLevel 1
    Abort "$(unableToUninstall)"
  ${EndIf}
!macroend

!macro NSIS_HOOK_PREINSTALL
  !insertmacro StopInstalledLambChat
  ; Updater and same-version reinstalls otherwise skip the existing uninstaller.
  ${If} ${FileExists} "$INSTDIR\uninstall.exe"
    SetOutPath $PLUGINSDIR
    ClearErrors
    ExecWait '"$INSTDIR\uninstall.exe" /S /UPDATE _?=$INSTDIR' $0
    ${If} ${Errors}
    ${OrIf} $0 != 0
      SetErrorLevel 1
      Abort "$(unableToUninstall)"
    ${EndIf}
    SetOutPath $INSTDIR
  ${EndIf}
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  !insertmacro StopInstalledLambChat
!macroend
