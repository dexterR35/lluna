#ifndef MyAppVersion
  #error MyAppVersion is required
#endif
#ifndef BuildProfile
  #define BuildProfile "cpu"
#endif

[Setup]
AppId={{7D4BE526-156F-4AA8-A678-BEAB627A2389}
AppName=Midgard
AppVersion={#MyAppVersion}
AppPublisher=Midgard
AppPublisherURL=https://github.com/dexterR35/midgard
AppSupportURL=https://github.com/dexterR35/midgard/issues
AppUpdatesURL=https://github.com/dexterR35/midgard/releases
DefaultDirName={localappdata}\Programs\Midgard
DefaultGroupName=Midgard
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\..\release
OutputBaseFilename=Midgard-{#MyAppVersion}-windows-x64-{#BuildProfile}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=yes
UninstallDisplayIcon={app}\Midgard.exe
SetupLogging=yes
MinVersion=10.0.17763

[Files]
Source: "..\..\dist\Midgard\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Midgard"; Filename: "{app}\Midgard.exe"
Name: "{autodesktop}\Midgard"; Filename: "{app}\Midgard.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Run]
Filename: "{app}\Midgard.exe"; Description: "Launch Midgard"; Flags: nowait postinstall skipifsilent

[Code]
function InitializeSetup(): Boolean;
begin
  Log('Midgard profile: {#BuildProfile}');
  Log('Python 3.12 is embedded in this package; no system Python is required.');
  Result := True;
  if ('{#BuildProfile}' = 'cuda') and
     (not FileExists(ExpandConstant('{sys}\nvidia-smi.exe'))) then
  begin
    MsgBox(
      'This is the CUDA build, but an NVIDIA driver was not detected.' + #13#10 +
      'Install a current NVIDIA driver or use the CPU build.',
      mbCriticalError,
      MB_OK
    );
    Result := False;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  LogDirectory: String;
begin
  if CurStep = ssInstall then
    WizardForm.StatusLabel.Caption :=
      'Installing Midgard and its embedded Python runtime...';
  if CurStep = ssDone then
  begin
    LogDirectory := ExpandConstant('{localappdata}\Midgard\logs');
    ForceDirectories(LogDirectory);
    FileCopy(
      ExpandConstant('{log}'),
      LogDirectory + '\installer.log',
      False
    );
  end;
end;
