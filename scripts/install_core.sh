#!/usr/bin/env bash
# install_core.sh  --  Server-side installer for the VPN IP update service.
#
# Run as root on a fresh Ubuntu/Debian server:
#   sudo bash scripts/install_core.sh
#
# What it does:
#   - Installs nginx, python3-venv, certbot (optional).
#   - Creates a dedicated non-privileged system user 'remoterefresh'.
#   - Sets up the nginx webroot at /var/www/html with required paths.
#   - Copies router/update_script.sh and router/domain_list.txt to the webroot.
#   - Generates /var/www/html/router/domain_list.txt.sha256.
#   - Creates scan-flag stubs (ip_scan_off.txt, port_scan_off.txt).
#   - Creates /etc/remote-refresh.env with runtime configuration.
#   - Installs and enables the systemd service.
#   - Creates data directories owned by remoterefresh.
#
# Requires the repository to be cloned at /opt/remote_refresh
# (or set REPO_DIR env var to override).

set -euo pipefail

REPO_DIR="${REPO_DIR:-/opt/remote_refresh}"
WEBROOT="/var/www/html"
ROUTER_DIR="$WEBROOT/router"
DATA_DIR="/var/lib/remote_refresh"
BOT_USER="remoterefresh"
BOT_GROUP="remoterefresh"
SERVICE_NAME="remote-refresh-bot"
ENV_FILE="/etc/remote-refresh.env"
DOMAIN_LIST_FILE="$ROUTER_DIR/domain_list.txt"

# -------- Helper --------
log() { echo "[install_core] $*"; }

require_root() {
  if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: must run as root (sudo $0)"
    exit 1
  fi
}

require_root

# -------- Dependencies --------
log "Installing dependencies..."
apt-get update -q
apt-get install -y -q nginx python3 python3-venv python3-pip sha256sum curl || \
  apt-get install -y -q nginx python3 python3-venv python3-pip curl

# -------- System user --------
if ! id "$BOT_USER" >/dev/null 2>&1; then
  useradd --system --no-create-home --shell /usr/sbin/nologin \
    --user-group "$BOT_USER"
  log "Created system user $BOT_USER"
else
  log "User $BOT_USER already exists"
fi

# -------- Directories --------
mkdir -p "$ROUTER_DIR" "$DATA_DIR"
chown "$BOT_USER:$BOT_GROUP" "$DATA_DIR"
# webroot router dir must be writable by the bot to update domain_list.txt
chown "$BOT_USER:$BOT_GROUP" "$ROUTER_DIR"
chmod 755 "$ROUTER_DIR"

# -------- Copy router worker from repo --------
WORKER_SRC="$REPO_DIR/router/update_script.sh"
if [ ! -f "$WORKER_SRC" ]; then
  log "ERROR: $WORKER_SRC not found. Is the repo cloned at $REPO_DIR?"
  exit 1
fi
cp -f "$WORKER_SRC" "$ROUTER_DIR/update_script.sh"
chmod 644 "$ROUTER_DIR/update_script.sh"
chown "$BOT_USER:$BOT_GROUP" "$ROUTER_DIR/update_script.sh"
log "Copied update_script.sh to $ROUTER_DIR"

# -------- Publish domain_list.txt --------
DOMAIN_LIST_SRC="$REPO_DIR/router/domain_list.txt"
if [ ! -f "$DOMAIN_LIST_SRC" ]; then
  log "WARNING: $DOMAIN_LIST_SRC not found, creating empty placeholder"
  echo "# domain_list.txt" > "$DOMAIN_LIST_FILE"
else
  cp -f "$DOMAIN_LIST_SRC" "$DOMAIN_LIST_FILE"
fi
chown "$BOT_USER:$BOT_GROUP" "$DOMAIN_LIST_FILE"
chmod 644 "$DOMAIN_LIST_FILE"
log "Published domain_list.txt to $ROUTER_DIR"

# Generate domain_list.txt.sha256
sha256sum "$DOMAIN_LIST_FILE" > "${DOMAIN_LIST_FILE}.sha256"
chown "$BOT_USER:$BOT_GROUP" "${DOMAIN_LIST_FILE}.sha256"
chmod 644 "${DOMAIN_LIST_FILE}.sha256"
log "Generated ${DOMAIN_LIST_FILE}.sha256"

# -------- Scan flags --------
for flag in ip_scan_off.txt port_scan_off.txt; do
  dst="$WEBROOT/$flag"
  if [ ! -f "$dst" ]; then
    echo "0" > "$dst"
    chown "$BOT_USER:$BOT_GROUP" "$dst"
    log "Created flag file $dst"
  fi
done

# -------- IP file placeholder --------
IP_FILE="$WEBROOT/current_vpn_ip.txt"
if [ ! -f "$IP_FILE" ]; then
  echo "" > "$IP_FILE"
  chown "$BOT_USER:$BOT_GROUP" "$IP_FILE"
  chmod 644 "$IP_FILE"
  log "Created $IP_FILE"
else
  chown "$BOT_USER:$BOT_GROUP" "$IP_FILE"
fi

# -------- Environment file --------
cat > "$ENV_FILE" <<EOF
# /etc/remote-refresh.env  --  runtime config for $SERVICE_NAME
# Populate BOT_TOKEN and ALLOWED_IDS before starting the service.
BOT_TOKEN=your-telegram-bot-token-here
ALLOWED_IDS=123456789

IP_FILE=$WEBROOT/current_vpn_ip.txt
HISTORY_FILE=$DATA_DIR/history.log
IP_SCAN_FLAG=$WEBROOT/ip_scan_off.txt
PORT_SCAN_FLAG=$WEBROOT/port_scan_off.txt
DOMAIN_LIST_FILE=$DOMAIN_LIST_FILE
EOF
chmod 640 "$ENV_FILE"
chown "root:$BOT_GROUP" "$ENV_FILE"
log "Created $ENV_FILE (edit BOT_TOKEN and ALLOWED_IDS)"

# -------- Python venv --------
VENV_DIR="$DATA_DIR/venv"
if [ ! -d "$VENV_DIR" ]; then
  python3 -m venv "$VENV_DIR"
  chown -R "$BOT_USER:$BOT_GROUP" "$VENV_DIR"
fi
sudo -u "$BOT_USER" "$VENV_DIR/bin/pip" install --quiet \
  -r "$REPO_DIR/bot/requirements.txt"
log "Python venv ready at $VENV_DIR"

# -------- Systemd service --------
SERVICE_SRC="$REPO_DIR/scripts/${SERVICE_NAME}.service"
if [ ! -f "$SERVICE_SRC" ]; then
  log "ERROR: $SERVICE_SRC not found"
  exit 1
fi
cp -f "$SERVICE_SRC" "/etc/systemd/system/${SERVICE_NAME}.service"
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
log "Systemd service $SERVICE_NAME installed and enabled"

# -------- nginx --------
# nginx default config serves /var/www/html -- nothing extra needed for plain files.
systemctl enable nginx
systemctl restart nginx
log "nginx restarted"

log ""
log "=== Installation complete ==="
log "Edit $ENV_FILE with your BOT_TOKEN and ALLOWED_IDS, then:"
log "  systemctl start $SERVICE_NAME"
log "  systemctl status $SERVICE_NAME"
