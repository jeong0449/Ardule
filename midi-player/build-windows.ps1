# build-windows.ps1
# Build Ardule MIDI Player for Windows (PyInstaller onedir)

$ErrorActionPreference = "Stop"

$Root = $PSScriptRoot
$Source = Join-Path $Root "ardule-midi-player.py"
$BuildDir = Join-Path $Root "build"
$DistDir = Join-Path $Root "dist"
$AppDir = Join-Path $DistDir "ArduleMIDIPlayer"
$DemoSource = Join-Path $Root "samples\ardule-midi-player-demo.mid"
$DemoTarget = Join-Path $AppDir "ardule-midi-player-demo.mid"

Write-Host "=== Ardule MIDI Player: Windows build ==="

# Check required files/directories
if (-not (Test-Path $Source)) {
    throw "Source file not found: $Source"
}

foreach ($dir in @("fluidsynth", "soundfont", "licenses")) {
    $path = Join-Path $Root $dir
    if (-not (Test-Path $path)) {
        throw "Required directory not found: $path"
    }
}

if (-not (Test-Path $DemoSource)) {
    throw "Demo MIDI not found: $DemoSource"
}

# Clean previous build
Write-Host "[1/4] Cleaning previous build..."
if (Test-Path $BuildDir) {
    Remove-Item $BuildDir -Recurse -Force
}
if (Test-Path $DistDir) {
    Remove-Item $DistDir -Recurse -Force
}

# Build EXE
Write-Host "[2/4] Running PyInstaller..."
py -m PyInstaller `
    --noconfirm `
    --clean `
    --onedir `
    --name ArduleMIDIPlayer `
    --workpath $BuildDir `
    --distpath $DistDir `
    $Source

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed."
}

# Copy runtime components
Write-Host "[3/4] Copying runtime files..."

Copy-Item `
    (Join-Path $Root "fluidsynth") `
    (Join-Path $AppDir "fluidsynth") `
    -Recurse

Copy-Item `
    (Join-Path $Root "soundfont") `
    (Join-Path $AppDir "soundfont") `
    -Recurse

Copy-Item `
    (Join-Path $Root "licenses") `
    (Join-Path $AppDir "licenses") `
    -Recurse

# Put the demo MIDI directly beside the EXE so it is immediately visible
# when Ardule MIDI Player starts in its distribution directory.
Copy-Item $DemoSource $DemoTarget

# Final check
Write-Host "[4/4] Checking distribution..."

$Exe = Join-Path $AppDir "ArduleMIDIPlayer.exe"

if (-not (Test-Path $Exe)) {
    throw "Build completed but EXE was not found: $Exe"
}

if (-not (Test-Path $DemoTarget)) {
    throw "Build completed but demo MIDI was not found: $DemoTarget"
}

Write-Host ""
Write-Host "=== Build complete ==="
Write-Host "Distribution:"
Write-Host "  $AppDir"
Write-Host ""
Write-Host "Executable:"
Write-Host "  $Exe"
Write-Host ""
Write-Host "Demo MIDI:"
Write-Host "  $DemoTarget"
