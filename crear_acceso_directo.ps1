$ErrorActionPreference = 'Stop'
$projectPath = $PSScriptRoot
$desktopPath = [Environment]::GetFolderPath('Desktop')
$pythonWindowless = Join-Path $projectPath '.venv\Scripts\pythonw.exe'
if (-not (Test-Path -LiteralPath $pythonWindowless)) {
    $pythonWindowless = (& python -c "import sys; from pathlib import Path; print(Path(sys.executable).with_name('pythonw.exe'))").Trim()
}
if (-not (Test-Path -LiteralPath $pythonWindowless)) {
    throw 'No se encuentra pythonw.exe. Instale Python o ejecute iniciar.bat primero.'
}
$shortcutPath = Join-Path $desktopPath 'Anonimizador.lnk'
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $pythonWindowless
$shortcut.Arguments = '"' + (Join-Path $projectPath 'app.py') + '"'
$shortcut.WorkingDirectory = $projectPath
$shortcut.IconLocation = (Join-Path $projectPath 'assets\anonimizador.ico') + ',0'
$shortcut.Description = 'Anonimizar archivos y restaurar el original'
$shortcut.Save()
Write-Output "Acceso directo creado: $shortcutPath"
