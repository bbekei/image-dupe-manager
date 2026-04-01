; DejaView NSIS installer hooks
; Tauri's built-in uninstall only removes $APPDATA\${BUNDLEID} (com.dejaview.app),
; but the Python sidecar stores application data under $APPDATA\DejaView.
; This hook removes that directory when the user opts to delete app data.

!macro NSIS_HOOK_POSTUNINSTALL
  ${If} $DeleteAppDataCheckboxState = 1
  ${AndIf} $UpdateMode <> 1
    SetShellVarContext current
    RmDir /r "$APPDATA\DejaView"
  ${EndIf}
!macroend
