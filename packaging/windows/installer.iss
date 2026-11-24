; Inno Setup definition for Parley.
;
; Build with build-installer.ps1, which passes AppVersion, SourceDir and
; OutputDir on the command line.

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "dist\Parley"
#endif
#ifndef OutputDir
  #define OutputDir "release"
#endif

[Setup]
AppId={{7F2C4C1E-2E8C-4B9E-9E31-9B0B0C6A2F41}
AppName=Parley
AppVersion={#AppVersion}
AppVerName=Parley {#AppVersion}
AppPublisher=Parley contributors
AppPublisherURL=https://github.com/Jonatas-Goncalves/Parley
AppSupportURL=https://github.com/Jonatas-Goncalves/Parley/issues
AppUpdatesURL=https://github.com/Jonatas-Goncalves/Parley/releases
DefaultDirName={autopf}\Parley
DefaultGroupName=Parley
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir={#OutputDir}
OutputBaseFilename=Parley-Setup-{#AppVersion}
SetupIconFile=..\..\assets\icons\parley.ico
UninstallDisplayIcon={app}\Parley.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; \
    GroupDescription: "Additional icons:"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Parley"; Filename: "{app}\Parley.exe"
Name: "{autodesktop}\Parley"; Filename: "{app}\Parley.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Parley.exe"; Description: "Launch Parley"; \
    Flags: nowait postinstall skipifsilent
