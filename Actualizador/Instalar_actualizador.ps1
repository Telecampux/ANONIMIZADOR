$ErrorActionPreference = 'Stop'

$installation = Join-Path $env:LOCALAPPDATA 'Anonimizador\Actualizador'
$desktop = [Environment]::GetFolderPath('DesktopDirectory')
$icon = Join-Path $PSScriptRoot '..\assets\anonimizador.ico'
if (-not (Test-Path -LiteralPath $icon -PathType Leaf)) {
    throw 'No se encuentra el logo. Extraiga el ZIP completo antes de instalar.'
}

New-Item -ItemType Directory -Path $installation -Force | Out-Null
foreach ($name in @('actualizar.py', 'Actualizar.bat')) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination (Join-Path $installation $name) -Force
}
Copy-Item -LiteralPath $icon -Destination (Join-Path $installation 'anonimizador.ico') -Force

$shortcutPath = Join-Path $desktop 'Actualizar Anonimizador.lnk'
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = Join-Path $installation 'Actualizar.bat'
$shortcut.WorkingDirectory = $installation
$shortcut.IconLocation = (Join-Path $installation 'anonimizador.ico') + ',0'
$shortcut.Description = 'Descargar y actualizar el software Anonimizador'
$shortcut.Save()
Write-Host "Actualizador instalado: $installation"
Write-Host "Acceso directo creado: $shortcutPath"
