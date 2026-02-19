; installer.iss — Inno Setup script for DejaView (plan §Phase 7).
;
; Prerequisites:
;   1. Run PyInstaller first:  pyinstaller dejaview.spec --noconfirm
;   2. Inno Setup 6 must be installed (https://jrsoftware.org/isinfo.php)
;   3. Build with: iscc installer.iss
;
; Output: installer/DejaView_Setup.exe

#define MyAppName "DejaView"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "DejaView"
#define MyAppExeName "DejaView.exe"
#define MyAppURL "https://github.com/dejaview"

[Setup]
AppId={{B7F8C4E1-5A2D-4F3E-9B6C-1D8E0F2A3B5C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppSupportURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=installer
OutputBaseFilename=DejaView_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
; Uncomment when a .ico file is added:
; SetupIconFile=resources\icons\dejaview.ico
; UninstallDisplayIcon={app}\DejaView.exe

; Windows 10+ only (plan §Requirements)
MinVersion=10.0

; Hungarian language support (plan §Phase 7 — Inno Setup installer with Hungarian language option)
[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "hungarian"; MessagesFile: "compiler:Languages\Hungarian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Bundle the entire PyInstaller output directory
Source: "dist\DejaView\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
