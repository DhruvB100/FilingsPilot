#!/bin/sh
# builds functions.zip = function_app.py + host.json + requirements.txt + backend/ + sql/
# then: az functionapp deployment source config-zip -g rg-filingspilot -n <function name> --src functions.zip --build-remote true
set -e
cd "$(dirname "$0")/.."
rm -rf build/function functions.zip
mkdir -p build/function
cp functions/function_app.py functions/host.json functions/requirements.txt build/function/
cp -r backend sql build/function/
rm -rf build/function/backend/__pycache__
cd build/function && python -c "import shutil; shutil.make_archive('../../functions', 'zip', '.')"
echo "built functions.zip"
