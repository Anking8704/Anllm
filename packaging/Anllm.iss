[Setup]
AppId={{C6D89681-515A-4D47-9468-5B7BB51C32A1}
AppName=Anllm
AppVersion=1.4
AppPublisher=Anllm
DefaultDirName={code:DefaultInstallDir}
DefaultGroupName=Anllm
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir=..\..\outputs
OutputBaseFilename=Anllm-Setup-1.4-x64
SetupIconFile=Anllm.ico
UninstallDisplayIcon={app}\Anllm-Icon-1.4.ico
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
DiskSpanning=no
UsePreviousAppDir=yes

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Default.isl,ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建 Anllm 桌面快捷方式"; GroupDescription: "快捷方式："; Flags: checkedonce

[Files]
Source: "dist\Anllm\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "Anllm.ico"; DestDir: "{app}"; DestName: "Anllm-Icon-1.4.ico"; Flags: ignoreversion

[Icons]
Name: "{group}\Anllm"; Filename: "{app}\Anllm.exe"; WorkingDir: "{app}"; IconFilename: "{app}\Anllm-Icon-1.4.ico"; AppUserModelID: "Anllm.Desktop"
Name: "{autodesktop}\Anllm"; Filename: "{app}\Anllm.exe"; WorkingDir: "{app}"; IconFilename: "{app}\Anllm-Icon-1.4.ico"; AppUserModelID: "Anllm.Desktop"; Tasks: desktopicon
Name: "{autodesktop}\Anllm"; Filename: "{app}\Anllm.exe"; WorkingDir: "{app}"; IconFilename: "{app}\Anllm-Icon-1.4.ico"; AppUserModelID: "Anllm.Desktop"; Check: UpdateExistingDesktopIcon

[Run]
Filename: "{app}\Anllm.exe"; Description: "启动 Anllm"; Flags: nowait postinstall skipifsilent

[Code]
function UpdateExistingDesktopIcon: Boolean;
begin
  Result := (not WizardIsTaskSelected('desktopicon')) and FileExists(ExpandConstant('{autodesktop}\Anllm.lnk'));
end;

procedure SHChangeNotify(EventID: Longint; Flags: Cardinal; Item1, Item2: String);
  external 'SHChangeNotify@shell32.dll stdcall';
procedure SHChangeNotifyAll(EventID: Longint; Flags: Cardinal; Item1, Item2: Longint);
  external 'SHChangeNotify@shell32.dll stdcall';

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then begin
    { Refresh Explorer's old icons without restarting Explorer. PATHW | FLUSH. }
    SHChangeNotify($00002000, $1005, ExpandConstant('{app}\Anllm.exe'), '');
    SHChangeNotify($00002000, $1005, ExpandConstant('{uninstallexe}'), '');
    SHChangeNotify($00002000, $1005, ExpandConstant('{autodesktop}\Anllm.lnk'), '');
    SHChangeNotify($00002000, $1005, ExpandConstant('{group}\Anllm.lnk'), '');
    SHChangeNotify($00001000, $1005, ExpandConstant('{app}'), '');
    SHChangeNotifyAll($08000000, $1000, 0, 0);
  end;
end;

function DefaultInstallDir(Param: String): String;
begin
  if DirExists('R:\') then Result := 'R:\Anllm'
  else Result := ExpandConstant('{localappdata}\Anllm');
end;


