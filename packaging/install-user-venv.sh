#!/bin/sh
# Install SinkSwitch using an isolated venv (no PyInstaller). Most reliable on arbitrary distros.
#
# From a clone or tarball of the repo (directory that contains run_app.py and requirements.txt):
#   ./packaging/install-user-venv.sh
#
# Installs:
#   ~/.local/share/sinkswitch/venv     — Python deps
#   ~/.local/bin/sinkswitch-venv         — launcher (add ~/.local/bin to PATH if needed)

set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [ ! -f "$ROOT/run_app.py" ] || [ ! -f "$ROOT/requirements.txt" ]; then
	echo "Expected repo root with run_app.py and requirements.txt (got $ROOT)." >&2
	exit 1
fi

DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
VENVDIR="$DATA/sinkswitch/venv"
BINDIR="${XDG_BIN_HOME:-$HOME/.local/bin}"

mkdir -p "$VENVDIR" "$BINDIR"
python3 -m venv "$VENVDIR"
"$VENVDIR/bin/python" -m pip install -U pip >/dev/null
"$VENVDIR/bin/pip" install -r "$ROOT/requirements.txt"

LAUNCH="$BINDIR/sinkswitch-venv"
{
	echo "#!/bin/sh"
	echo "export PYTHONPATH=\"$ROOT/src\""
	echo "exec \"$VENVDIR/bin/python\" \"$ROOT/run_app.py\" \"\$@\""
} >"$LAUNCH"
chmod +x "$LAUNCH"

echo "Installed venv: $VENVDIR"
echo "Launcher:       $LAUNCH"
echo "Run: $LAUNCH"
echo "(Keep this repo path stable, or reinstall after moving the tree.)"
