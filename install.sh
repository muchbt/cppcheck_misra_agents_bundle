#!/bin/bash
# MISRA Pipeline CLI Installer for Linux/macOS
# Usage:
#   curl -sSL https://repo/install.sh | sh
#   ./install.sh [--version vX.Y.Z] [--url <download-url>] [--repo-url <repo-url>]
#
# Environment variables:
#   MISRA_PIPELINE_DOWNLOAD_URL  - Override download URL
#   MISRA_PIPELINE_REPO_URL      - Override repository URL (for git fallback)

set -e

# ── Defaults ─────────────────────────────────────────────────────────────────
DEFAULT_REPO_URL="https://github.com/muchbt/cppcheck_misra_agents_bundle_v2"
REPO_URL="${MISRA_PIPELINE_REPO_URL:-$DEFAULT_REPO_URL}"

INSTALL_DIR="${HOME}/.misra-pipeline"
BIN_DIR="${INSTALL_DIR}/bin"
CLI_DIR="${BIN_DIR}/cli"
CONFIG_FILE="${INSTALL_DIR}/config.json"

VERSION=""
EXPLICIT_URL=""

# ── Parse arguments ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --version|-v)
            VERSION="$2"
            shift 2
            ;;
        --url|-u)
            EXPLICIT_URL="$2"
            shift 2
            ;;
        --repo-url)
            REPO_URL="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: $0 [--version vX.Y.Z] [--url <url>] [--repo-url <url>]"
            echo ""
            echo "Options:"
            echo "  --version, -v    Version to install (default: latest from repo)"
            echo "  --url, -u        Direct download URL for the agents archive"
            echo "  --repo-url       Git repository URL (for fallback)"
            echo ""
            echo "Environment variables:"
            echo "  MISRA_PIPELINE_DOWNLOAD_URL  - Override download URL"
            echo "  MISRA_PIPELINE_REPO_URL      - Override repository URL"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information."
            exit 1
            ;;
    esac
done

# Use environment variable or explicit argument for URL
DOWNLOAD_URL="${EXPLICIT_URL:-${MISRA_PIPELINE_DOWNLOAD_URL:-}}"

# Determine version
if [[ -z "$VERSION" ]]; then
    # Try to get latest version from repo
    if command -v git &> /dev/null; then
        VERSION=$(git ls-remote --tags "$REPO_URL" 2>/dev/null | tail -1 | sed 's|.*/v|v|' | sed 's/\^{}//') || true
    fi
    # Fallback to main if no tags found
    if [[ -z "$VERSION" ]]; then
        VERSION="main"
    fi
fi

echo "Installing MISRA Pipeline CLI..."
echo "  Version: $VERSION"
echo "  Repo:    $REPO_URL"

# ── Check prerequisites ──────────────────────────────────────────────────────
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 is required but not installed."
    exit 1
fi

# ── Create directory structure ───────────────────────────────────────────────
mkdir -p "$CLI_DIR"

# ── Download ─────────────────────────────────────────────────────────────────
download_success=false

# 1. Try explicit/environment URL first
if [[ -n "$DOWNLOAD_URL" ]]; then
    echo "Downloading from specified URL..."
    if curl -sSL -o "${INSTALL_DIR}/temp.tar.gz" "$DOWNLOAD_URL" 2>/dev/null; then
        echo "Extracting archive..."
        if tar -xzf "${INSTALL_DIR}/temp.tar.gz" -C "$BIN_DIR" --strip-components=1 2>/dev/null; then
            download_success=true
        else
            # Try without strip-components (archive might be flat)
            mkdir -p "${INSTALL_DIR}/temp_extract"
            if tar -xzf "${INSTALL_DIR}/temp.tar.gz" -C "${INSTALL_DIR}/temp_extract" 2>/dev/null; then
                # Find cli directory inside extracted content
                if [[ -d "${INSTALL_DIR}/temp_extract/cli" ]]; then
                    cp -r "${INSTALL_DIR}/temp_extract/cli/"* "$CLI_DIR/"
                    download_success=true
                else
                    # Assume extracted content is the cli directory itself
                    cp -r "${INSTALL_DIR}/temp_extract/"* "$CLI_DIR/"
                    download_success=true
                fi
                rm -rf "${INSTALL_DIR}/temp_extract"
            fi
        fi
        rm -f "${INSTALL_DIR}/temp.tar.gz"
    fi
fi

# 2. Try GitHub Release URL
if [[ "$download_success" != "true" ]]; then
    RELEASE_URL="${REPO_URL}/releases/download/${VERSION}/agents-${VERSION}.tar.gz"
    echo "Trying release download: $RELEASE_URL"
    if curl -sSL -o "${INSTALL_DIR}/temp.tar.gz" "$RELEASE_URL" 2>/dev/null; then
        echo "Extracting release archive..."
        mkdir -p "${INSTALL_DIR}/temp_extract"
        if tar -xzf "${INSTALL_DIR}/temp.tar.gz" -C "${INSTALL_DIR}/temp_extract" 2>/dev/null; then
            # Find cli directory in extracted archive
            if [[ -d "${INSTALL_DIR}/temp_extract/cli" ]]; then
                cp -r "${INSTALL_DIR}/temp_extract/cli/"* "$CLI_DIR/"
                download_success=true
            else
                # Check nested folder like agents-v1.0.0/cli
                nested_cli=$(find "${INSTALL_DIR}/temp_extract" -type d -name "cli" | head -1)
                if [[ -n "$nested_cli" ]]; then
                    cp -r "${nested_cli}/"* "$CLI_DIR/"
                    download_success=true
                fi
            fi
        fi
        rm -rf "${INSTALL_DIR}/temp_extract"
        rm -f "${INSTALL_DIR}/temp.tar.gz"
    fi
fi

# 3. Fallback to git archive
if [[ "$download_success" != "true" ]]; then
    echo "Release download failed, falling back to git archive..."
    if ! command -v git &> /dev/null; then
        echo "Error: git is required for fallback download but not installed."
        exit 1
    fi

    if git archive --remote="$REPO_URL" "$VERSION" -- cli/ 2>/dev/null | tar -x -C "$BIN_DIR"; then
        download_success=true
    fi
fi

if [[ "$download_success" != "true" ]]; then
    echo "Error: Failed to download CLI from any source."
    echo "Tips:"
    echo "  - Ensure the version tag exists in the repository"
    echo "  - For private repos, ensure git credentials are configured"
    echo "  - You can specify a direct URL with --url or MISRA_PIPELINE_DOWNLOAD_URL"
    exit 1
fi

# ── Create wrapper script ────────────────────────────────────────────────────
WRAPPER_SCRIPT="$BIN_DIR/misra-pipeline"
cat > "$WRAPPER_SCRIPT" << 'WRAPPER_EOF'
#!/bin/bash
# MISRA Pipeline CLI wrapper
python3 "${HOME}/.misra-pipeline/bin/cli/misra-pipeline-cli.py" "$@"
WRAPPER_EOF
chmod +x "$WRAPPER_SCRIPT"

# ── Create default configuration ─────────────────────────────────────────────
if [[ ! -f "$CONFIG_FILE" ]]; then
    cat > "$CONFIG_FILE" << CONFIG_EOF
{
  "repo_url": "${REPO_URL}",
  "download": {
    "mode": "release",
    "url_template": "{repo_url}/releases/download/{version}/agents-{version}.tar.gz",
    "fallback_mode": "git_archive"
  }
}
CONFIG_EOF
    echo "Created default configuration: $CONFIG_FILE"
fi

# ── Add to PATH ──────────────────────────────────────────────────────────────
PATH_LINE='export PATH="${HOME}/.misra-pipeline/bin:${PATH}"'

for profile in "${HOME}/.bashrc" "${HOME}/.zshrc" "${HOME}/.profile"; do
    if [[ -f "$profile" ]] && ! grep -q 'misra-pipeline/bin' "$profile" 2>/dev/null; then
        echo "$PATH_LINE" >> "$profile"
        echo "Added PATH to $profile"
        break
    fi
done

# ── Show success message ─────────────────────────────────────────────────────
INSTALLED_VERSION=$(cat "$CLI_DIR/VERSION" 2>/dev/null || echo "$VERSION")
echo ""
echo "Installation complete!"
echo "  CLI version: $INSTALLED_VERSION"
echo "  Install dir: $INSTALL_DIR"
echo "  Config file: $CONFIG_FILE"
echo ""
echo "To use immediately in this session:"
echo "  export PATH=\"${HOME}/.misra-pipeline/bin:\${PATH}\""
echo ""
echo "Then run:"
echo "  misra-pipeline init"
echo ""
echo "To use a custom download source:"
echo "  misra-pipeline config set repo_url <your-repo-url>"
echo "  misra-pipeline config set url_template '<your-url-template>'"
