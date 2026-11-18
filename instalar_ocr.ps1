$ErrorActionPreference = 'Stop'
$ocrExecutable = Join-Path $env:ProgramFiles 'Tesseract-OCR\tesseract.exe'
if (-not (Test-Path -LiteralPath $ocrExecutable) -and -not (Get-Command tesseract -ErrorAction SilentlyContinue)) {
    & winget install --id UB-Mannheim.TesseractOCR --exact --source winget --silent --accept-package-agreements --accept-source-agreements --disable-interactivity
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo instalar Tesseract OCR.' }
}
$dataPath = Join-Path $PSScriptRoot 'tessdata'
New-Item -ItemType Directory -Path $dataPath -Force | Out-Null
foreach ($language in @('spa', 'eng')) {
    $destination = Join-Path $dataPath ($language + '.traineddata')
    if (-not (Test-Path -LiteralPath $destination)) {
        $temporaryDownload = $destination + '.download'
        Invoke-WebRequest -Uri ('https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/' + $language + '.traineddata') -OutFile $temporaryDownload
        Move-Item -LiteralPath $temporaryDownload -Destination $destination -Force
    }
}
Write-Output 'OCR local instalado con español e inglés.'
