@echo off
REM MISRA Pipeline CLI Installer for Windows
REM Usage: install.bat [--version vX.Y.Z]

setlocal enabledelayedexpansion

set REPO_URL=https://github.com/muchbt/cppcheck_misra_agents_bundle_v2
set INSTALL_DIR=%USERPROFILE%\.misra-pipeline
set BIN_DIR=%INSTALL_DIR%\bin
set CLI_DIR=%BIN_DIR%\cli
set VERSION=%1
if "%VERSION%"=="" set VERSION=main

echo Installing MISRA Pipeline CLI...

REM 1. Check prerequisites
where python >nul 2>&1
if errorlevel 1 (
    echo Error: python is required but not installed.
    exit /b 1
)

where git >nul 2>&1
if errorlevel 1 (
    echo Error: git is required but not installed.
    exit /b 1
)

REM 2. Create directory structure
if not exist "%CLI_DIR%" mkdir "%CLI_DIR%"

REM 3. Download CLI from Git repository
echo Downloading CLI from %REPO_URL% (%VERSION%)...

REM Use PowerShell to download and extract
powershell -NoProfile -Command ^
    "$url = '%REPO_URL%/archive/refs/heads/main.zip'; ^
     $zip = '%INSTALL_DIR%\temp.zip'; ^
     $temp = '%INSTALL_DIR%\temp'; ^
     try { ^
         Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing; ^
         Expand-Archive -Path $zip -DestinationPath $temp -Force; ^
         $folder = Get-ChildItem -Path $temp -Directory | Select-Object -First 1; ^
         Copy-Item -Path ($folder.FullName + '\cli\*') -Destination '%CLI_DIR%' -Recurse -Force; ^
         Remove-Item $zip -Force; ^
         Remove-Item $temp -Recurse -Force; ^
         Write-Host 'Download complete'; ^
     } catch { ^
         Write-Host ('Error: ' + $_.Exception.Message); ^
         exit 1; ^
     }"

if errorlevel 1 (
    echo Error: Failed to download CLI.
    exit /b 1
)

REM 4. Create wrapper batch file
set WRAPPER=%BIN_DIR%\misra-pipeline.bat
(
echo @echo off
echo python "%CLI_DIR%\misra-pipeline-cli.py" %%*
) > "%WRAPPER%"

REM 5. Add to PATH (user environment variable)
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

REM 6. Show success message
set INSTALLED_VERSION=unknown
if exist "%CLI_DIR%\VERSION" (
    set /p INSTALLED_VERSION=<"%CLI_DIR%\VERSION"
)

echo.
echo Installation complete!
echo   CLI version: %INSTALLED_VERSION%
echo   Install dir: %INSTALL_DIR%
echo.
echo You may need to restart your terminal for PATH changes to take effect.
echo.
echo Then run:
echo   misra-pipeline init

endlocal