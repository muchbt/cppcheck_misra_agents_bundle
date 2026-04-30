@echo off
REM MISRA Pipeline CLI Installer for Windows
REM Usage: install.bat [--version vX.Y.Z] [--url <download-url>] [--repo-url <repo-url>]
REM
c REM Environment variables:
REM   MISRA_PIPELINE_DOWNLOAD_URL  - Override download URL
REM   MISRA_PIPELINE_REPO_URL      - Override repository URL (for fallback)

setlocal enabledelayedexpansion

REM ── Defaults ───────────────────────────────────────────────────────────────
set "DEFAULT_REPO_URL=https://github.com/muchbt/cppcheck_misra_agents_bundle_v2"
if defined MISRA_PIPELINE_REPO_URL (
    set "REPO_URL=!MISRA_PIPELINE_REPO_URL!"
) else (
    set "REPO_URL=!DEFAULT_REPO_URL!"
)

set "INSTALL_DIR=%USERPROFILE%\.misra-pipeline"
set "BIN_DIR=%INSTALL_DIR%\bin"
set "CLI_DIR=%BIN_DIR%\cli"
set "CONFIG_FILE=%INSTALL_DIR%\config.json"

set "VERSION="
set "EXPLICIT_URL="

REM ── Parse arguments ────────────────────────────────────────────────────────
:parse_args
if "%~1"=="" goto args_done
if "%~1"=="--version" (
    set "VERSION=%~2"
    shift
    shift
    goto parse_args
)
if "%~1"=="-v" (
    set "VERSION=%~2"
    shift
    shift
    goto parse_args
)
if "%~1"=="--url" (
    set "EXPLICIT_URL=%~2"
    shift
    shift
    goto parse_args
)
if "%~1"=="-u" (
    set "EXPLICIT_URL=%~2"
    shift
    shift
    goto parse_args
)
if "%~1"=="--repo-url" (
    set "REPO_URL=%~2"
    shift
    shift
    goto parse_args
)
if "%~1"=="--help" (
    echo Usage: install.bat [--version vX.Y.Z] [--url ^<url^>] [--repo-url ^<url^>]
    echo.
    echo Options:
    echo   --version, -v    Version to install (default: latest from repo)
    echo   --url, -u        Direct download URL for the agents archive
    echo   --repo-url       Git repository URL (for fallback)
    echo.
    echo Environment variables:
    echo   MISRA_PIPELINE_DOWNLOAD_URL  - Override download URL
    echo   MISRA_PIPELINE_REPO_URL      - Override repository URL
    exit /b 0
)
echo Unknown option: %~1
echo Use --help for usage information.
exit /b 1

:args_done

REM ── Determine version ──────────────────────────────────────────────────────
if "!VERSION!=="" (
    REM Try to get latest version from git tags
    for /f "delims=" %%i in ('git ls-remote --tags "!REPO_URL!" 2^>nul ^| findstr "refs/tags/v" ') do (
        for /f "tokens=2 delims=/" %%j in ("%%i") do set "VERSION=%%j"
    )
    REM Remove ^{} suffix if present
    set "VERSION=!VERSION:^{}=!"
)
if "!VERSION!=="" set "VERSION=main"

REM ── Determine download URL ─────────────────────────────────────────────────
if defined EXPLICIT_URL (
    set "DOWNLOAD_URL=!EXPLICIT_URL!"
) else if defined MISRA_PIPELINE_DOWNLOAD_URL (
    set "DOWNLOAD_URL=!MISRA_PIPELINE_DOWNLOAD_URL!"
) else (
    set "DOWNLOAD_URL="
)

echo Installing MISRA Pipeline CLI...
echo   Version: !VERSION!
echo   Repo:    !REPO_URL!

REM ── Check prerequisites ────────────────────────────────────────────────────
where python >nul 2>&1
if errorlevel 1 (
    echo Error: python is required but not installed.
    exit /b 1
)

REM ── Create directory structure ─────────────────────────────────────────────
if not exist "!CLI_DIR!" mkdir "!CLI_DIR!"

REM ── Download ───────────────────────────────────────────────────────────────
set "download_success=false"
set "TEMP_ZIP=!INSTALL_DIR!\temp.zip"
set "TEMP_DIR=!INSTALL_DIR!\temp"

REM 1. Try explicit/environment URL first
if defined DOWNLOAD_URL (
    echo Downloading from specified URL...
    powershell -NoProfile -Command ^
        "try { Invoke-WebRequest -Uri '!DOWNLOAD_URL!' -OutFile '!TEMP_ZIP!' -UseBasicParsing; Write-Host 'Download complete'; exit 0; } catch { Write-Host ('Error: ' + $_.Exception.Message); exit 1; }"
    if !errorlevel! equ 0 (
        echo Extracting archive...
        powershell -NoProfile -Command ^
            "try { Expand-Archive -Path '!TEMP_ZIP!' -DestinationPath '!TEMP_DIR!' -Force; Write-Host 'Extracted'; exit 0; } catch { Write-Host ('Error: ' + $_.Exception.Message); exit 1; }"
        if !errorlevel! equ 0 (
            REM Look for cli directory in extracted content
            if exist "!TEMP_DIR!\cli" (
                xcopy /E /I /Y "!TEMP_DIR!\cli\*" "!CLI_DIR!\"
                set "download_success=true"
            ) else (
                REM Check nested folder
                for /f "delims=" %%d in ('powershell -NoProfile -Command "Get-ChildItem -Path '!TEMP_DIR!' -Directory | Select-Object -First 1 | ForEach-Object { $_.FullName }"') do (
                    if exist "%%d\cli" (
                        xcopy /E /I /Y "%%d\cli\*" "!CLI_DIR!\"
                        set "download_success=true"
                    )
                )
            )
        )
        if exist "!TEMP_ZIP!" del /F /Q "!TEMP_ZIP!"
        if exist "!TEMP_DIR!" rmdir /S /Q "!TEMP_DIR!"
    )
)

REM 2. Try GitHub Release URL
if "!download_success!==false" (
    set "RELEASE_URL=!REPO_URL!/releases/download/!VERSION!/agents-!VERSION!.tar.gz"
    echo Trying release download: !RELEASE_URL!
    powershell -NoProfile -Command ^
        "try { Invoke-WebRequest -Uri '!RELEASE_URL!' -OutFile '!TEMP_ZIP!' -UseBasicParsing; Write-Host 'Download complete'; exit 0; } catch { Write-Host ('Release not found: ' + $_.Exception.Message); exit 1; }"
    if !errorlevel! equ 0 (
        echo Extracting release archive...
        mkdir "!TEMP_DIR!" 2>nul
        tar -xzf "!TEMP_ZIP!" -C "!TEMP_DIR!" 2>nul
        if !errorlevel! equ 0 (
            echo Extracted
            if exist "!TEMP_DIR!\cli" (
                xcopy /E /I /Y "!TEMP_DIR!\cli\*" "!CLI_DIR!\"
                set "download_success=true"
            ) else (
                for /f "delims=" %%d in ('powershell -NoProfile -Command "Get-ChildItem -Path '!TEMP_DIR!' -Directory | Select-Object -First 1 | ForEach-Object { $_.FullName }"') do (
                    if exist "%%d\cli" (
                        xcopy /E /I /Y "%%d\cli\*" "!CLI_DIR!\"
                        set "download_success=true"
                    )
                )
            )
        ) else (
            echo Error: failed to extract tar.gz
        )
        if exist "!TEMP_ZIP!" del /F /Q "!TEMP_ZIP!"
        if exist "!TEMP_DIR!" rmdir /S /Q "!TEMP_DIR!"
    )
)

REM 3. Fallback to git archive
if "!download_success!==false" (
    echo Release download failed, falling back to git archive...
    where git >nul 2>&1
    if errorlevel 1 (
        echo Error: git is required for fallback download but not installed.
        exit /b 1
    )

    REM Use git archive and extract
    git archive --remote="!REPO_URL!" "!VERSION!" -- cli/ 2>nul >"!TEMP_ZIP!"
    if !errorlevel! equ 0 (
        REM git archive outputs tar, use PowerShell to extract
        powershell -NoProfile -Command ^
            "try { $tar = [System.IO.File]::ReadAllBytes('!TEMP_ZIP!'); $ms = New-Object System.IO.MemoryStream(, $tar); $gz = New-Object System.IO.Compression.GzipStream($ms, [System.IO.Compression.CompressionMode]::Decompress); $out = New-Object System.IO.FileStream('!TEMP_DIR!.tar', [System.IO.FileMode]::Create); $gz.CopyTo($out); $out.Close(); tar -xf '!TEMP_DIR!.tar' -C '!BIN_DIR!'; Write-Host 'Extracted'; exit 0; } catch { Write-Host ('Error: ' + $_.Exception.Message); exit 1; }"
        if !errorlevel! equ 0 (
            set "download_success=true"
        )
    )
    if exist "!TEMP_ZIP!" del /F /Q "!TEMP_ZIP!"
    if exist "!TEMP_DIR!.tar" del /F /Q "!TEMP_DIR!.tar"
)

if "!download_success!==false" (
    echo Error: Failed to download CLI from any source.
    echo Tips:
    echo   - Ensure the version tag exists in the repository
    echo   - For private repos, ensure git credentials are configured
    echo   - You can specify a direct URL with --url or MISRA_PIPELINE_DOWNLOAD_URL
    exit /b 1
)

REM ── Create wrapper batch file ──────────────────────────────────────────────
set "WRAPPER=!BIN_DIR!\misra-pipeline.bat"
(
echo @echo off
echo python "%%USERPROFILE%%\.misra-pipeline\bin\cli\misra-pipeline-cli.py" %%*
) > "!WRAPPER!"

REM ── Create default configuration ───────────────────────────────────────────
if not exist "!CONFIG_FILE!" (
    (
    echo {
    echo   "repo_url": "!REPO_URL!",
    echo   "download": {
    echo     "mode": "release",
    echo     "url_template": "{repo_url}/releases/download/{version}/agents-{version}.tar.gz",
    echo     "fallback_mode": "git_archive"
    echo   }
    echo }
    ) > "!CONFIG_FILE!"
    echo Created default configuration: !CONFIG_FILE!
)

REM ── Add to PATH ────────────────────────────────────────────────────────────
echo Adding to PATH...
powershell -NoProfile -Command ^
    "$path = [Environment]::GetEnvironmentVariable('PATH', 'User'); ^
     $bin = '%BIN_DIR%'; ^
     if ($path -notlike '*misra-pipeline*') { ^
         [Environment]::SetEnvironmentVariable('PATH', $bin + ';' + $path, 'User'); ^
         Write-Host 'PATH updated'; ^
     } else { ^
         Write-Host 'PATH already contains misra-pipeline'; ^
     }"

REM ── Show success message ───────────────────────────────────────────────────
set "INSTALLED_VERSION=unknown"
if exist "!CLI_DIR!\VERSION" (
    set /p INSTALLED_VERSION=<"!CLI_DIR!\VERSION"
)

echo.
echo Installation complete!
echo   CLI version: !INSTALLED_VERSION!
echo   Install dir: !INSTALL_DIR!
echo   Config file: !CONFIG_FILE!
echo.
echo You may need to restart your terminal for PATH changes to take effect.
echo.
echo Then run:
echo   misra-pipeline init
echo.
echo To use a custom download source:
echo   misra-pipeline config set repo_url ^<your-repo-url^>
echo   misra-pipeline config set url_template ^<your-url-template^>

endlocal
