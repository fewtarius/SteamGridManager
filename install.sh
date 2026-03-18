#!/bin/bash
# SGM (SteamGrid Manager) installer for SteamOS / Linux
#
# Installs sgm to ~/.local/share/sgm and creates ~/.local/bin/sgm
#
# Usage:
#   bash install.sh              (run from the repo directory)
#   curl -fsSL <url> | bash      (remote install)
#
set -euo pipefail

INSTALL_DIR="$HOME/.local/share/sgm"
BIN_DIR="$HOME/.local/bin"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# All python files that make up sgm
SGM_FILES=(
    sgm.py
    config.py
    steam.py
    backup.py
    refresh.py
    monitor.py
    systems.py
    rom_scanner.py
    shortcuts.py
    art_scraper.py
    portable.py
    sources.py
)

echo ""
echo "  SteamGrid Manager (sgm) Installer"
echo ""

# Check python3
if ! command -v python3 &>/dev/null; then
    echo "  ERROR: python3 not found. Install Python 3.10+ first."
    exit 1
fi

# Check python version
PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
    echo "  ERROR: Python 3.10+ required (found $PY_VER)"
    exit 1
fi
echo "  Python $PY_VER found"

# Create directories
mkdir -p "$INSTALL_DIR" "$BIN_DIR"

# Copy source files
echo "  Installing to $INSTALL_DIR ..."
for f in "${SGM_FILES[@]}"; do
    src="$SCRIPT_DIR/$f"
    if [ -f "$src" ]; then
        cp "$src" "$INSTALL_DIR/"
    else
        echo "  ERROR: $f not found in $SCRIPT_DIR"
        exit 1
    fi
done
chmod +x "$INSTALL_DIR/sgm.py"
# Create ./sgm symlink in install dir for direct invocation from the repo
ln -sf sgm.py "$INSTALL_DIR/sgm"
echo "  Copied ${#SGM_FILES[@]} files"

# Copy extras if present
for extra in requirements.txt sgm-monitor.service sgm-monitor.timer; do
    if [ -f "$SCRIPT_DIR/$extra" ]; then
        cp "$SCRIPT_DIR/$extra" "$INSTALL_DIR/"
    fi
done

# Install requests
echo "  Checking dependencies..."
if python3 -c "import requests" 2>/dev/null; then
    echo "  requests OK"
else
    echo "  Installing requests..."
    pip3 install --user -q requests 2>/dev/null \
        || python3 -m pip install --user -q requests 2>/dev/null \
        || {
            echo ""
            echo "  WARNING: Could not install 'requests' automatically."
            echo "  Install it manually:  pip install requests"
            echo "  Or on SteamOS:        sudo pacman -S python-requests"
            echo ""
        }
fi

# Create launcher
cat > "$BIN_DIR/sgm" << 'EOF'
#!/bin/bash
exec python3 "$HOME/.local/share/sgm/sgm.py" "$@"
EOF
chmod +x "$BIN_DIR/sgm"

# Check if ~/.local/bin is in PATH
if echo "$PATH" | tr ':' '\n' | grep -qx "$BIN_DIR"; then
    PATH_OK=true
else
    PATH_OK=false
fi

# Add to PATH if needed
if [ "$PATH_OK" = false ]; then
    # Add to .bashrc if not already there
    PROFILE="$HOME/.bashrc"
    PATH_LINE='export PATH="$HOME/.local/bin:$PATH"'
    if [ -f "$PROFILE" ] && grep -qF '.local/bin' "$PROFILE"; then
        echo "  PATH entry already in .bashrc"
    else
        echo "" >> "$PROFILE"
        echo '# Added by sgm installer' >> "$PROFILE"
        echo "$PATH_LINE" >> "$PROFILE"
        echo "  Added ~/.local/bin to PATH in .bashrc"
    fi
    export PATH="$BIN_DIR:$PATH"
fi

echo ""
echo "  Done! sgm v$(python3 "$INSTALL_DIR/sgm.py" --version 2>/dev/null | awk '{print $2}' || echo '1.0.0') installed."
echo ""
echo "  Get started:"
echo "    sgm config init    # first-time setup"
echo "    sgm status         # check current state"
echo "    sgm backup         # back up your grid images"
echo ""
if [ "$PATH_OK" = false ]; then
    echo "  NOTE: Run 'source ~/.bashrc' or open a new terminal for PATH changes."
    echo ""
fi
