@echo off
setlocal EnableExtensions
cd /d "%~dp0.."

echo ==^> Memoria 发布包构建（输出: Package\）
python packaging\build.py %*
if errorlevel 1 exit /b %errorlevel%

if not exist "Package\Memoria.exe" (
  echo 构建结束但未找到 Package\Memoria.exe
  exit /b 1
)

echo.
echo ==^> 完成: %cd%\Package\Memoria.exe
echo     分发整个 Package\ 文件夹即可。
echo     本地试运行: scripts\run_release.cmd
exit /b 0
