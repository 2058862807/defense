$ErrorActionPreference = 'Stop'

$desktop = [Environment]::GetFolderPath('Desktop')
$lnkPath = Join-Path $desktop 'PROTEAN DEFENSE.lnk'

$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut($lnkPath)
$sc.TargetPath = 'C:\Windows\System32\wsl.exe'
$sc.Arguments = '-d Ubuntu-24.04 -- bash /mnt/c/Users/Dustin/defense_v2/scripts/launch_dashboard.sh'
$sc.WorkingDirectory = 'C:\Users\Dustin\defense_v2'
$sc.IconLocation = 'C:\Users\Dustin\defense_v2\icons\defense.ico'
$sc.Description = 'Start PROTEAN DEFENSE stack (backend 8080 + frontend 3000) and open the dashboard'
$sc.Save()

Write-Output "Created: $lnkPath"
Write-Output "Target:  $($sc.TargetPath) $($sc.Arguments)"
Write-Output "Icon:    $($sc.IconLocation)"
