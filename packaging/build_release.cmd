@echo off
setlocal EnableExtensions
cd /d "%~dp0.."

rem 优先使用项目虚拟环境（pyinstaller/webview 依赖均装在其内）；无则回退系统 python
set "PYTHON_EXE=python"
if exist ".venv\Scripts\python.exe" set "PYTHON_EXE=%~dp0..\.venv\Scripts\python.exe"

echo ==^> Memoria 发布包构建（输出: Package\）
"%PYTHON_EXE%" packaging\build.py %*
if errorlevel 1 exit /b %errorlevel%

if not exist "Package\Memoria.exe" (
  echo 构建结束但未找到 Package\Memoria.exe
  exit /b 1
)

echo.
echo ==^> 完成: %cd%\Package\Memoria.exe
echo     分发整个 Package\ 文件夹即可。
echo     本地试运行: packaging\run_release.cmd
exit /b 0
