#ifndef AppVersion
  #error AppVersion must be supplied by the pinned build
#endif
[Setup]
AppId=CadenceMCPBridge-{#AppVersion}
AppName=Cadence MCP Bridge
AppVersion={#AppVersion}
AppVerName=Cadence MCP Bridge {#AppVersion} (Preview)
AppPublisher=Phjrab
AppPublisherURL=https://github.com/Phjrab/cadence-mcp-bridge
DefaultDirName={localappdata}\Programs\CadenceMCPBridge\{#AppVersion}
UsePreviousAppDir=no
DefaultGroupName=Cadence MCP Bridge {#AppVersion}
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
DisableProgramGroupPage=yes
DisableDirPage=no
UninstallDisplayIcon={app}\CadenceMCPBridgeSetup.exe
LicenseFile={#Payload}\LICENSE
InfoAfterFile={#Payload}\INSTALL.md
OutputDir={#Output}
OutputBaseFilename=CadenceMCPBridge-{#AppVersion}-windows-x64-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=no
RestartApplications=no
SetupLogging=yes
VersionInfoVersion=2.2.0.1
VersionInfoProductVersion=2.2.0.1
VersionInfoProductTextVersion={#AppVersion}
Uninstallable=yes

[Files]
Source: "{#Payload}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Cadence MCP Bridge 설정"; Filename: "{app}\CadenceMCPBridgeSetup.exe"
Name: "{group}\제거"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\CadenceMCPBridgeSetup.exe"; Description: "최초 설정 도우미 열기"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\CadenceMCPBridge.exe"; Parameters: "--host-uninstall"; Flags: runhidden waituntilterminated; RunOnceId: "RemoveExactOwnedCodexEntry"

[Code]
function CreateFile(FileName: String; Access, Share: LongWord; Security: LongWord;
  Creation, Flags, Template: LongWord): THandle;
  external 'CreateFileW@kernel32.dll stdcall';
function CloseHandle(Handle: THandle): Boolean;
  external 'CloseHandle@kernel32.dll stdcall';

function FilesAvailable(DirectoryName: String): Boolean;
var
  Item: TFindRec;
  Handle: THandle;
  FileName: String;
begin
  Result := True;
  if FindFirst(DirectoryName + '\*', Item) then begin
    try
      repeat
        if (Item.Name <> '.') and (Item.Name <> '..') and
           (Item.Name <> 'unins000.exe') and (Item.Name <> 'unins000.dat') then begin
          FileName := DirectoryName + '\' + Item.Name;
          if (Item.Attributes and FILE_ATTRIBUTE_DIRECTORY) <> 0 then begin
            if not FilesAvailable(FileName) then Result := False;
          end else begin
            Handle := CreateFile(FileName, $80000000, 0, 0, 3, 0, 0);
            if Handle = THandle(-1) then Result := False
            else CloseHandle(Handle);
          end;
        end;
      until not FindNext(Item) or not Result;
    finally
      FindClose(Item);
    end;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if DirExists(ExpandConstant('{app}')) and not FilesAvailable(ExpandConstant('{app}')) then
    Result := 'Files are in use or inaccessible. Finish active work and close this bridge version normally; no process was terminated.';
end;

function InitializeUninstall(): Boolean;
begin
  Result := FilesAvailable(ExpandConstant('{app}'));
  if not Result then
    MsgBox('Bridge files are in use or inaccessible. Finish active work and close this version normally before uninstalling. No process was terminated.', mbError, MB_OK);
end;

function InitializeSetup(): Boolean;
begin
  Result := True;
  if not WizardSilent then
    Result := MsgBox('This preview installs per user, without changing system Python or PATH. It does not include Cadence/PDK, configure SSH, contact a VM or submit simulations. Continue?', mbConfirmation, MB_OKCANCEL) = IDOK;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if CurStep = ssPostInstall then begin
    if not Exec(ExpandConstant('{app}\CadenceMCPBridge.exe'), '--host-verify', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
      RaiseException('Installed runtime could not start. Setup evidence is retained; do not configure a client.');
    if ResultCode <> 0 then
      RaiseException('Installed payload verification failed. Setup evidence is retained; do not configure a client.');
    SaveStringToFile(ExpandConstant('{app}\INSTALLATION.json'), '{"version":"{#AppVersion}","kind":"per-user"}', False);
  end;
end;
