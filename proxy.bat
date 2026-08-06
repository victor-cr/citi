@echo off

set CURRENT_DIR=%~dp0
mkdir %CURRENT_DIR%data
cd %CURRENT_DIR%

git pull -r
python -m pip install --upgrade pip
python -m pip install pyyaml regex requests
python "%CURRENT_DIR%plugin.proxy.py" "%CURRENT_DIR%data"