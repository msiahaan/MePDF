; Inno Setup 6 Script for MePDF (Windows x64 Installer)

#define MyAppName "MePDF"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "msiahaan"
#define MyAppURL "https://github.com/msiahaan/MePDF"
#define MyAppExeName "MePDF.exe"

[Setup]
AppId={{8F6E7A92-4C1D-4B28-9E15-3A8D91B20E47}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
LicenseFile=..\..\LICENSE
OutputDir=..\..\dist\installers
OutputBaseFilename=MePDF-Setup-{#MyAppVersion}-win64
SetupIconFile=..\..\assets\mepdf.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ChangesAssociations=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "associatepdf"; Description: "Register {#MyAppName} in 'Open with' menu for .pdf files"; GroupDescription: "File Associations:"

[Files]
Source: "..\..\dist\MePDF\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; Register MePDF ProgID for optional .pdf "Open with" integration
Root: HKA; Subkey: "Software\Classes\MePDF.Document"; ValueType: string; ValueName: ""; ValueData: "PDF Document"; Flags: uninsdeletekey; Tasks: associatepdf
Root: HKA; Subkey: "Software\Classes\MePDF.Document\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"; Tasks: associatepdf
Root: HKA; Subkey: "Software\Classes\MePDF.Document\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Tasks: associatepdf
Root: HKA; Subkey: "Software\Classes\.pdf\OpenWithProgids"; ValueType: string; ValueName: "MePDF.Document"; ValueData: ""; Flags: uninsdeletevalue; Tasks: associatepdf

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
