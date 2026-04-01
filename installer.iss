; ============================================================
; Copilot+ PC - NPU Demo Installer
; InnoSetup script - builds a single setup.exe
; ============================================================
; Build with: "C:\Users\frankbu\AppData\Local\Programs\Inno Setup 6\ISCC.exe" installer.iss

#define MyAppName "NPU Demo - Copilot+ PC"
#define MyAppVersion "1.0"
#define MyAppPublisher "Microsoft Surface"
#define MyAppURL "https://github.com/frankcx1/surface-npu-demo"

[Setup]
AppId={{B7A3D2F1-4E5C-4A8B-9D6E-1F2A3B4C5D6E}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
DefaultDirName={userpf}\NPU-Demo
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=C:\temp\npu-dist\dist
OutputBaseFilename=NPU-Demo-Setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
SetupIconFile=compiler:SetupClassicIcon.ico
UninstallDisplayName={#MyAppName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
WelcomeLabel1=Welcome to the {#MyAppName} Setup
WelcomeLabel2=This will install the on-device AI demo app for Surface Copilot+ PCs.%n%nThe app runs AI entirely on your device using the NPU. No cloud, no data egress.%n%nAfter installation, a one-time setup will install Foundry Local and download the AI model (~3 GB).
FinishedHeadingLabel=Installation Complete
FinishedLabel=The NPU Demo has been installed.%n%nClick "Launch Setup" below to complete the one-time configuration (installs Foundry Local + downloads AI model).%n%nAfter setup completes, use the Start Menu shortcut "Start NPU Demo" to launch.

[Tasks]
Name: "desktopicon"; Description: "Create a Desktop shortcut"; GroupDescription: "Additional options:"
Name: "runsetup"; Description: "Run first-time setup now (installs Foundry Local + model)"; GroupDescription: "Additional options:"; Flags: checkedonce

[Files]
; Main app (PyInstaller bundle)
Source: "C:\temp\npu-dist\dist\npu-demo\npu-demo.exe"; DestDir: "{app}\app"; Flags: ignoreversion
Source: "C:\temp\npu-dist\dist\npu-demo\_internal\*"; DestDir: "{app}\app\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs

; Launcher scripts
Source: "start-demo.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "stop-demo.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "setup.ps1"; DestDir: "{app}"; Flags: ignoreversion

; Vision service
Source: "vision-service\AppPackages\*"; DestDir: "{app}\vision-service\AppPackages"; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist
Source: "vision-service\scripts\setup-cert.ps1"; DestDir: "{app}\vision-service\scripts"; Flags: ignoreversion skipifsourcedoesntexist
Source: "vision-service\scripts\launch-vision.ps1"; DestDir: "{app}\vision-service\scripts"; Flags: ignoreversion skipifsourcedoesntexist

; Logo files
Source: "surface-logo.png"; DestDir: "{app}\app"; Flags: ignoreversion skipifsourcedoesntexist
Source: "copilot-logo.avif"; DestDir: "{app}\app"; Flags: ignoreversion skipifsourcedoesntexist
Source: "flagstar-logo-official.png"; DestDir: "{app}\app"; Flags: ignoreversion skipifsourcedoesntexist

; README
Source: "C:\temp\npu-dist\dist\npu-demo\README.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Start NPU Demo"; Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File ""{app}\start-demo.ps1"""; WorkingDir: "{app}"; Comment: "Start all services and open browser"
Name: "{group}\Stop NPU Demo"; Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File ""{app}\stop-demo.ps1"""; WorkingDir: "{app}"; Comment: "Stop all services"
Name: "{group}\README"; Filename: "{app}\README.txt"
Name: "{group}\Uninstall NPU Demo"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Start NPU Demo"; Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File ""{app}\start-demo.ps1"""; WorkingDir: "{app}"; Tasks: desktopicon; Comment: "Start all services and open browser"

[Run]
; Run setup.ps1 after install if user checked the option
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File ""{app}\setup.ps1"""; WorkingDir: "{app}"; Description: "Launch first-time setup (Foundry Local + model download)"; Flags: nowait postinstall skipifsilent; Tasks: runsetup
; Always offer to start the demo
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File ""{app}\start-demo.ps1"""; WorkingDir: "{app}"; Description: "Start NPU Demo now"; Flags: nowait postinstall skipifsilent unchecked

[UninstallRun]
; Stop services before uninstall
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File ""{app}\stop-demo.ps1"""; WorkingDir: "{app}"; Flags: runhidden

