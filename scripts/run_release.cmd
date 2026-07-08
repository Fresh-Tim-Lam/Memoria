@echo off
setlocal EnableExtensions
cd /d "%~dp0.."

if not exist "Package\Memoria.exe" (
  echo 未找到发布包，请先运行: scripts\build_release.cmd
  exit /b 1
)

cd /d "Package"
set MEMORIA_MODE=release
set MEMORIA_SHELL=pyqt6
"Memoria.exe" %*
