param(
    [string]$Model = "small",
    [switch]$OnlyLaunch
)

$ErrorActionPreference = "Stop"
# Keep stderr output from Python/pip visible instead of converting it into truncated PowerShell exceptions.
$PSNativeCommandUseErrorActionPreference = $false

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvDir = Join-Path $ScriptRoot ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$DepsStamp = Join-Path $VenvDir ".deps_ready"
$RequirementsFile = Join-Path $ScriptRoot "requirements-win.txt"
$GuiScript = Join-Path $ScriptRoot "whisper_gui_win.py"
$ModelsDir = Join-Path $ScriptRoot "models"
$FfmpegDir = Join-Path $ScriptRoot "ffmpeg"
$ModelDownloader = Join-Path $ScriptRoot "download_model.py"

function Write-Step([string]$Message) {
    Write-Host "[Whisper Win] $Message" -ForegroundColor Cyan
}

function Resolve-BasePython {
    $candidates = @(
        @{Exe = "py"; Args = @("-3.12", "-c", "import sys; print(sys.executable)")},
        @{Exe = "py"; Args = @("-3", "-c", "import sys; print(sys.executable)")},
        @{Exe = "python"; Args = @("-c", "import sys; print(sys.executable)")}
    )

    foreach ($candidate in $candidates) {
        if (-not (Get-Command $candidate.Exe -ErrorAction SilentlyContinue)) {
            continue
        }
        try {
            $output = & $candidate.Exe @($candidate.Args) 2>$null
            if ($LASTEXITCODE -ne 0) {
                continue
            }
            $resolved = ($output | Select-Object -Last 1).Trim()
            if ($resolved -and (Test-Path $resolved)) {
                return $resolved
            }
        } catch {
            continue
        }
    }

    $searchRoots = @(
        "$env:LocalAppData\Programs\Python",
        "$env:ProgramFiles\Python*"
    )
    foreach ($root in $searchRoots) {
        try {
            $found = Get-ChildItem -Path $root -Filter "python.exe" -Recurse -ErrorAction SilentlyContinue |
                Sort-Object LastWriteTime -Descending |
                Select-Object -First 1
            if ($found -and (Test-Path $found.FullName)) {
                return $found.FullName
            }
        } catch {
            continue
        }
    }

    return $null
}

function Install-PythonIfMissing {
    $basePython = Resolve-BasePython
    if ($basePython) {
        return $basePython
    }

    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "Python not found and winget is unavailable. Please install Python 3.12 and run again."
    }

    Write-Step "Python 3.12 not found. Installing with winget (first-time only)..."
    & winget install -e --id Python.Python.3.12 --scope user --silent --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) {
        throw "winget failed to install Python. Please install Python 3.12 manually and retry."
    }

    $basePython = Resolve-BasePython
    if (-not $basePython) {
        throw "Python installation completed but executable is still not visible in PATH. Open a new terminal and retry."
    }

    return $basePython
}

function Install-FfmpegLocally {
    $localFfmpeg = Join-Path $FfmpegDir "ffmpeg.exe"
    $localFfprobe = Join-Path $FfmpegDir "ffprobe.exe"
    if ((Test-Path $localFfmpeg) -and (Test-Path $localFfprobe)) {
        return
    }

    if (-not (Test-Path $FfmpegDir)) {
        New-Item -ItemType Directory -Path $FfmpegDir | Out-Null
    }

    Write-Step "Downloading FFmpeg portable binaries..."
    $zipPath = Join-Path $ScriptRoot "ffmpeg-release-essentials.zip"
    $extractDir = Join-Path $ScriptRoot "ffmpeg_extract"
    $url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

    if (Test-Path $zipPath) {
        Remove-Item -Force $zipPath
    }
    if (Test-Path $extractDir) {
        Remove-Item -Force -Recurse $extractDir
    }

    Invoke-WebRequest -Uri $url -OutFile $zipPath
    Expand-Archive -Path $zipPath -DestinationPath $extractDir -Force

    $ffmpegExe = Get-ChildItem -Path $extractDir -Filter "ffmpeg.exe" -Recurse | Select-Object -First 1
    $ffprobeExe = Get-ChildItem -Path $extractDir -Filter "ffprobe.exe" -Recurse | Select-Object -First 1

    if (-not $ffmpegExe -or -not $ffprobeExe) {
        throw "FFmpeg download completed but binaries were not found in the archive."
    }

    Copy-Item -Path $ffmpegExe.FullName -Destination $localFfmpeg -Force
    Copy-Item -Path $ffprobeExe.FullName -Destination $localFfprobe -Force

    Remove-Item -Force $zipPath
    Remove-Item -Force -Recurse $extractDir
}

function Ensure-VenvAndPackages {
    $basePython = Install-PythonIfMissing

    if (-not (Test-Path $VenvPython)) {
        Write-Step "Creating local virtual environment..."
        & $basePython -m venv $VenvDir
    }

    $needsInstall = -not (Test-Path $DepsStamp)
    if (-not $needsInstall) {
        & $VenvPython -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('opencc') else 1)" *> $null
        if ($LASTEXITCODE -ne 0) {
            $needsInstall = $true
        }
    }
    if (-not $needsInstall) {
        & $VenvPython -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('edge_tts') else 1)" *> $null
        if ($LASTEXITCODE -ne 0) {
            $needsInstall = $true
        }
    }

    if ($needsInstall) {
        Write-Step "Installing/updating Python dependencies..."
        & $VenvPython -m pip install --upgrade pip setuptools wheel
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to upgrade pip in local environment."
        }

        & $VenvPython -m pip install -r $RequirementsFile
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to install Python dependencies."
        }

        New-Item -ItemType File -Path $DepsStamp -Force | Out-Null
    }
}

function Ensure-Model([string]$ModelName) {
    if (-not (Test-Path $ModelsDir)) {
        New-Item -ItemType Directory -Path $ModelsDir | Out-Null
    }

    Write-Step "Preparing Whisper model: $ModelName"
    & $VenvPython $ModelDownloader $ModelName --output $ModelsDir
    if ($LASTEXITCODE -ne 0) {
        throw "Model download failed."
    }
}

function Launch-App {
    if (-not (Test-Path $VenvPython)) {
        throw "Environment not installed yet. Run 01-install-and-run.bat first."
    }
    if (-not (Test-Path $GuiScript)) {
        throw "Cannot find whisper_gui_win.py in the win folder."
    }

    $env:WHISPER_MODEL_DIR = $ModelsDir
    $env:PATH = "$FfmpegDir;$env:PATH"

    Write-Step "Launching Whisper GUI..."
    & $VenvPython $GuiScript
}

try {
    if (-not $OnlyLaunch) {
        Ensure-VenvAndPackages
        Install-FfmpegLocally
        Ensure-Model -ModelName $Model
    }
    Launch-App
    exit 0
} catch {
    Write-Host ""
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    if ($_.ScriptStackTrace) {
        Write-Host $($_.ScriptStackTrace) -ForegroundColor DarkGray
    }
    Write-Host "Tip: run 01-install-and-run.bat again with internet enabled."
    exit 1
}
