#!/bin/sh
# Build dist/Rubric.app. Uses a throwaway venv so nothing is installed globally.
set -e
cd "$(dirname "$0")"
python3 -m venv .build-venv
.build-venv/bin/pip install --quiet pyinstaller
.build-venv/bin/pyinstaller --noconfirm --windowed --name Rubric \
    --osx-bundle-identifier local.rubric run_rubric.py
echo "Built: $(pwd)/dist/Rubric.app"
