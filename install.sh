#!/bin/bash
# MISRA Pipeline CLI Installer for Linux
# Usage: curl -sSL https://repo/install.sh | sh
# Or:    ./install.sh [--version vX.Y.Z]

set -e

REPO_URL="https://github.com/muchbt/cppcheck_misra_agents_bundle_v2"
INSTALL_DIR="${HOME}/.misra-pipeline"
BIN_DIR="${INSTALL_DIR}/bin"
CLI_DIR="${BIN_DIR}/cli"
VERSION="${1:-main}"

echo "Installing MISRA Pipeline CLI..."

# 1. Check prerequisites
if ! command -v git &> /dev/null; then
    echo "Error: git is required but not installed."
    exit 1
fi

if ! command -v python3 &> /dev/null; then
    echo "Error: python3 is required but not installed."
    exit 1
fi

# 2. Create directory structure
mkdir -p "$CLI_DIR"

# 3. Download CLI from Git repository
echo "Downloading CLI from $REPO_URL ($VERSION)..."
git archive --remote="$REPO_URL" "$VERSION" -- cli/ | tar -x -C "$BIN_DIR" 2>/dev/null || {
    echo "Error: Failed to download CLI."
    echo "Tip: If using a specific version tag, ensure it exists in the repo."
    exit 1
}

# 4. Create wrapper script
WRAPPER_SCRIPT="$BIN_DIR/misra-pipeline"
cat > "$WRAPPER_SCRIPT" << 'WRAPPER_EOF'
#!/bin/bash
# MISRA Pipeline CLI wrapper
python3 "${HOME}/.misra-pipeline/bin/cli/misra-pipeline-cli.py" "$@"
WRAPPER_EOF
chmod +x "$WRAPPER_SCRIPT"

# 5. Add to PATH (user shell profile)
PATH_LINE='export PATH="${HOME}/.misra-pipeline/bin:${PATH}"'

for profile in "${HOME}/.bashrc" "${HOME}/.zshrc" "${HOME}/.profile"; do
    if [ -f "$profile" ] && ! grep -q 'misra-pipeline/bin' "$profile" 2>/dev/null; then
        echo "$PATH_LINE" >> "$profile"
        echo "Added PATH to $profile"
        break
    fi
done

# 6. Show success message
INSTALLED_VERSION=$(cat "$CLI_DIR/VERSION" 2>/dev/null || echo "$VERSION")
echo ""
echo "Installation complete!"
echo "  CLI version: $INSTALLED_VERSION"
echo "  Install dir: $INSTALL_DIR"
echo ""
echo "To use immediately in this session:"
echo "  export PATH=\"${HOME}/.misra-pipeline/bin:\${PATH}\""
echo ""
echo "Then run:"
echo "  misra-pipeline init"