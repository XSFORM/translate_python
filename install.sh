#!/usr/bin/env bash
# install.sh  --  Bootstrap installer for the VPN IP update service.
#
# Recommended: download and review the script before executing it.
#   curl -fsSL https://raw.githubusercontent.com/XSFORM/translate_python/main/install.sh \
#     -o /tmp/install.sh && less /tmp/install.sh && sudo bash /tmp/install.sh
#
# Quick one-liner (only use on a trusted network / verified repo):
#   curl -fsSL https://raw.githubusercontent.com/XSFORM/translate_python/main/install.sh | sudo bash
#
# Or if you already have the repo cloned:
#   sudo bash install.sh
#
# This script:
#   1. Re-executes itself with sudo if not already root.
#   2. Installs git if missing.
#   3. Clones this repository into /opt/remote_refresh.
#   4. Runs scripts/install_core.sh.

set -euo pipefail

REPO_URL="https://github.com/XSFORM/translate_python.git"
INSTALL_DIR="/opt/remote_refresh"

# Re-exec with sudo if not root
if [ "$(id -u)" -ne 0 ]; then
  exec sudo bash "$0" "$@"
fi

echo "[install] Installing git..."
apt-get update -q
apt-get install -y -q git

# Clone or update
if [ -d "$INSTALL_DIR/.git" ]; then
  echo "[install] Repository already cloned at $INSTALL_DIR, pulling latest..."
  git -C "$INSTALL_DIR" pull --ff-only
else
  echo "[install] Cloning repository into $INSTALL_DIR ..."
  git clone "$REPO_URL" "$INSTALL_DIR"
fi

echo "[install] Running install_core.sh ..."
REPO_DIR="$INSTALL_DIR" bash "$INSTALL_DIR/scripts/install_core.sh"
