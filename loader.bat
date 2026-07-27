@echo off

set CURRENT_DIR=%~dp0

mkdir %CURRENT_DIR%data

python "%CURRENT_DIR%plugin.loader.py" "%CURRENT_DIR%data"