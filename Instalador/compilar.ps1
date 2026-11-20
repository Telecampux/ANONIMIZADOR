$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $root

$python = (Get-Command py -ErrorAction Stop).Source
& $python -3.13 -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'No se pudieron instalar las dependencias.' }
& $python -3.13 -m pip install 'pyinstaller>=6,<7'
if ($LASTEXITCODE -ne 0) { throw 'No se pudo instalar PyInstaller.' }

$tesseract = Join-Path $env:ProgramFiles 'Tesseract-OCR'
if (-not (Test-Path (Join-Path $tesseract 'tesseract.exe'))) {
    throw 'Instale Tesseract OCR de UB Mannheim antes de compilar.'
}
$iscc = Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe'
if (-not (Test-Path $iscc)) { throw 'Instale Inno Setup 6 antes de compilar.' }

$models = Join-Path $root 'tessdata'
New-Item -ItemType Directory -Path $models -Force | Out-Null
foreach ($language in @('spa', 'eng')) {
    $model = Join-Path $models ($language + '.traineddata')
    if (-not (Test-Path $model)) {
        Invoke-WebRequest -Uri ('https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/' + $language + '.traineddata') -OutFile $model
    }
}

& $python -3.13 -m PyInstaller --noconfirm --clean --windowed --onedir --name EnigmaLex `
    --icon 'assets\anonimizador.ico' --add-data 'assets;assets' --add-data 'VERSION;.' `
    --add-data 'tessdata;tessdata' app.py
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller falló.' }

$ocrTarget = Join-Path $root 'dist\EnigmaLex\_internal\Tesseract-OCR'
New-Item -ItemType Directory -Path $ocrTarget -Force | Out-Null
Copy-Item (Join-Path $tesseract 'tesseract.exe') $ocrTarget
Get-ChildItem $tesseract -Filter '*.dll' -File | Copy-Item -Destination $ocrTarget

$version = (Get-Content (Join-Path $root 'VERSION') -Raw).Trim()
& $iscc ('/DAppVersion=' + $version) (Join-Path $root 'Instalador\EnigmaLex.iss')
if ($LASTEXITCODE -ne 0) { throw 'Inno Setup falló.' }
Write-Output (Join-Path $root ('instalador-dist\EnigmaLex-Setup-' + $version + '.exe'))
