#!/bin/sh
# Build a standalone binary with PyInstaller.
# Uses a project venv so no system pip/pyinstaller needed (works on Arch etc.).
# Output: dist/pipewire-audio-router

set -e
cd "$(dirname "$0")"
APP_DIR="$(pwd)"
VENV_DIR="${APP_DIR}/.venv-build"

if [ ! -d "$VENV_DIR" ]; then
    echo "Creating build venv at $VENV_DIR ..."
    python3 -m venv "$VENV_DIR"
fi
echo "Using venv: $VENV_DIR"
"$VENV_DIR/bin/pip" install -q pyinstaller
# App deps so PyInstaller can trace and bundle them (yaml, PyQt6, etc.)
"$VENV_DIR/bin/pip" install -q -r requirements.txt
"$VENV_DIR/bin/python" -m PyInstaller run_app.spec

echo ""
echo "Done. Binary: dist/pipewire-audio-router"
echo "Run: ./dist/pipewire-audio-router"
echo "Or move dist/pipewire-audio-router to your PATH or Desktop."
