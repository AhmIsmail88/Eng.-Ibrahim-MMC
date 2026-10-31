; ENG. IBRAHIM — Inno Setup 6 script (SPEC 26.6)
; Build the app first: scripts\build_windows.ps1
#define MyAppName "ENG. IBRAHIM"
#define MyAppVersion "0.10.0"
#define MyAppPublisher "ENG. IBRAHIM"
#define MyAppExeName "ENG_IBRAHIM.exe"

[Setup]
AppId={{8F3C2B7A-5D41-4E9B-9C3A-ENGIBRAHIM01}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist\installer
OutputBaseFilename=ENG_IBRAHIM_Installer_{#MyAppVersion}_x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\assets\icons\ENG_IBRAHIM_Icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; User-local install: no admin rights required (SPEC 26.6).
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
; Standalone build output. The database and attachments are NEVER installed here:
; they live in %LOCALAPPDATA%\ENG_IBRAHIM (SPEC 19.2, 26.6).
Source: "..\dist\ENG_IBRAHIM\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Intentionally empty: uninstalling must not delete user data (SPEC 26.6).
