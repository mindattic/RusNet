#!/usr/bin/env bash
# Install RusNet: set up a Python environment, install requirements.txt, and the rusnet CLI.
#
# By default this creates a local virtual environment in .venv and installs into it, so your
# system Python stays untouched. Pass --system to install into whatever `python3` resolves to
# (e.g. an already-activated venv) instead.
#
#   ./install.sh            # create .venv and install everything into it
#   ./install.sh --system   # install into the current Python instead of a venv
#
# The RusNet core is standard-library only; requirements.txt (pywebview, psutil) enables the
# native desktop viewer and cleaner interface enumeration. `pip install -e .` adds the rusnet CLI.
set -euo pipefail

cd "$(dirname "$0")"

SYSTEM=0
for arg in "$@"; do
  case "$arg" in
    --system) SYSTEM=1 ;;
    -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

# Find a Python 3.
PY=""
for c in python3 python; do
  if command -v "$c" >/dev/null 2>&1; then PY="$c"; break; fi
done
[ -n "$PY" ] || { echo "Python 3.9+ not found. Install it and re-run." >&2; exit 1; }

VER="$("$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
echo "Found Python $VER"
"$PY" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, 9) else 1)' \
  || { echo "Python $VER is too old; RusNet needs 3.9 or newer." >&2; exit 1; }

if [ "$SYSTEM" -eq 1 ]; then
  PYBIN="$PY"
  echo "Installing into the current Python (--system)."
else
  if [ ! -x ".venv/bin/python" ]; then
    echo "Creating virtual environment in .venv ..."
    "$PY" -m venv .venv
  else
    echo "Reusing existing .venv"
  fi
  PYBIN=".venv/bin/python"
fi

echo "Upgrading pip ..."
"$PYBIN" -m pip install --upgrade pip

echo "Installing requirements.txt ..."
"$PYBIN" -m pip install -r requirements.txt

echo "Installing the rusnet package (editable) ..."
"$PYBIN" -m pip install -e .

echo
echo "RusNet installed."
[ "$SYSTEM" -eq 1 ] || echo "Activate the environment with:  source .venv/bin/activate"
echo "Then try:"
echo "  python -m rusnet scan --open       # scan and open the report"
echo "  python -m rusnet.desktop            # native desktop viewer (with a Scan button)"
echo "  python -m rusnet viewer --open      # empty viewer; drop any RusNet .json on it"
