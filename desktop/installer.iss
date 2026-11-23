#define AppName "NEXCAP Desktop"
#define AppVersion "0.1.0"

[Setup]
AppId={{A582AC7A-B67F-4B51-ACBA-210EB286CB30}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=PetrDevelop
DefaultDirName={localappdata}\Programs\PetrDevelop\NEXCAP Desktop
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
Compression=lzma2
SolidCompression=yes
LicenseFile=..\LICENSE
SetupIconFile=nexcap.ico
OutputDir=dist
OutputBaseFilename=NEXCAP-Desktop-PetrDevelop-Setup-x64
UninstallDisplayIcon={app}\NEXCAP Desktop.exe

[Files]
Source: "dist\NEXCAP Desktop\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autoprograms}\NEXCAP Desktop"; Filename: "{app}\NEXCAP Desktop.exe"
