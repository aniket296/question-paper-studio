; ============================================================================
; Inno Setup Script for Question Paper Studio (Windows 64-bit Installer)
; Packages PyInstaller --onedir bundle (dist/QuestionPaperStudio/) into
; Output/Setup_QuestionPaperStudio.exe with Desktop/Start Menu shortcuts
; and .qpf Question Paper Archive file associations.
; ============================================================================

#define MyAppName "Question Paper Studio"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Question Paper Studio"
#define MyAppExeName "QuestionPaperStudio.exe"
#define MyAppAssocName "Question Paper Studio Archive"
#define MyAppAssocExt ".qpf"
#define MyAppAssocKey StringChange(MyAppAssocName, " ", "") + MyAppAssocExt

[Setup]
AppId={{B4A1E9D2-7C8F-4A1E-9C3B-5D8E2F4A6B1C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\QuestionPaperStudio
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
ChangesAssociations=yes
OutputDir=..\Output
OutputBaseFilename=Setup_QuestionPaperStudio
SetupIconFile=..\assets\icons\app_icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "associateqpf"; Description: "Associate {#MyAppAssocExt} Question Paper files with {#MyAppName}"; GroupDescription: "File Associations:"

[Files]
Source: "..\dist\QuestionPaperStudio\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\QuestionPaperStudio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Software\Classes\{#MyAppAssocExt}\OpenWithProgids"; ValueType: string; ValueName: "{#MyAppAssocKey}"; ValueData: ""; Flags: uninsdeletevalue; Tasks: associateqpf
Root: HKA; Subkey: "Software\Classes\{#MyAppAssocKey}"; ValueType: string; ValueName: ""; ValueData: "{#MyAppAssocName}"; Flags: uninsdeletekey; Tasks: associateqpf
Root: HKA; Subkey: "Software\Classes\{#MyAppAssocKey}\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"; Tasks: associateqpf
Root: HKA; Subkey: "Software\Classes\{#MyAppAssocKey}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Tasks: associateqpf
Root: HKA; Subkey: "Software\Classes\Applications\{#MyAppExeName}\SupportedTypes"; ValueType: string; ValueName: "{#MyAppAssocExt}"; ValueData: ""; Tasks: associateqpf

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
