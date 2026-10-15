# Build a shareable Windows package for PEB Designer
#
# Usage (from peb-designer folder, with venv active):
#   powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "Installing PyInstaller..."
.\.venv\Scripts\python -m pip install -q "pyinstaller>=6.0"

# Ensure sections DB exists under data/ for bundling
Write-Host "Preparing data\sections.db..."
.\.venv\Scripts\python -c "from app.database.sections import SectionDatabase, DEFAULT_DB_PATH; from pathlib import Path; import shutil; db=SectionDatabase(); src=DEFAULT_DB_PATH; dest=Path('data')/'sections.db'; dest.parent.mkdir(exist_ok=True); shutil.copy2(src, dest); print('bundled', dest)"

Write-Host "Building (this can take several minutes)..."
.\.venv\Scripts\pyinstaller --noconfirm --clean peb_designer.spec

$Dist = Join-Path $Root "dist\PEBDesigner"
$Zip = Join-Path $Root "dist\PEBDesigner-Windows.zip"

if (Test-Path $Zip) { Remove-Item $Zip -Force }

Write-Host "Creating zip..."
Compress-Archive -Path $Dist -DestinationPath $Zip -Force

# Copy how-to next to zip
Copy-Item (Join-Path $Root "docs\HOW_TO_TEST.txt") (Join-Path $Root "dist\HOW_TO_TEST.txt") -Force

Write-Host ""
Write-Host "DONE"
Write-Host "Send this file to testers: $Zip"
Write-Host "They unzip and run PEBDesigner\PEBDesigner.exe"
Write-Host ""
Get-Item $Zip | Format-List FullName, Length, LastWriteTime
