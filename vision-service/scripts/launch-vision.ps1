# Launch the vision service MSIX app
$shell = New-Object -ComObject Shell.Application
$shell.ShellExecute('shell:AppsFolder\Microsoft.NPUDemo.VisionService_r0xr04974zwaa!App')
Write-Host "Launched vision service. Check http://localhost:5100/health"
