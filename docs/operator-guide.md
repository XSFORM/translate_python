# Operator Guide

This document is for system maintainers only. It is intentionally kept out of the main README.

## Architecture overview

- **Server**: Linux VPS running nginx + Telegram bot.
  - Publishes the current OpenVPN server IP at `http://<domain>/current_vpn_ip.txt`.
  - Publishes the domain list at `http://<domain>/router/domain_list.txt` (+ `.sha256`).
  - Publishes the router worker at `http://<domain>/router/update_script.sh`.
  - Manages scan flags (`ip_scan_off.txt`, `port_scan_off.txt`).

- **Routers** (Padavan firmware, BusyBox `/bin/sh`):
  - `router/update_script.sh` runs every 15 min via cron.
  - If the OpenVPN tunnel is up → exits immediately (no network fetch).
  - If the tunnel is down → fetches a fresh IP from the domain list, rewrites `client.conf`, and reloads OpenVPN.

## Server installation

```bash
sudo bash install.sh
```

Then edit `/etc/remote-refresh.env`:
- `BOT_TOKEN`: your Telegram bot token from BotFather.
- `ALLOWED_IDS`: comma-separated Telegram user IDs.

Start the service:
```bash
sudo systemctl start remote-refresh-bot
sudo systemctl status remote-refresh-bot
```

## Router installation

Run on the router as root:
```sh
wget -qO /tmp/bootstrap.sh http://<your-domain>/router/bootstrap.sh && sh /tmp/bootstrap.sh
```

Or with the bootstrap one-liner if wget supports piping:
```sh
wget -qO- http://<your-domain>/router/bootstrap.sh | sh
```

## Bot commands / buttons

| Button            | Action                                                    |
|-------------------|-----------------------------------------------------------|
| 📡 Current IP     | Shows the IP currently served to routers                  |
| ✏️ Set IP         | Update the served IP (validates IPv4, logs to history)    |
| 📋 History        | Shows the last 20 IP-change events                        |
| 🔍 IP Scan toggle | Toggles `ip_scan_off.txt` (pause IP polling on routers)   |
| 🔍 Port Scan toggle | Toggles `port_scan_off.txt`                             |
| 🌐 Domains        | Add / remove domains in `domain_list.txt` (+ regen `.sha256`) |

## Domain list management

The bot's Domains button lets you add or remove domains interactively. After each change the bot rewrites `domain_list.txt` and regenerates `domain_list.txt.sha256`.

Manual edit: update `/var/www/html/router/domain_list.txt` (one host per line, `#` comments allowed), then run:
```bash
sha256sum /var/www/html/router/domain_list.txt > /var/www/html/router/domain_list.txt.sha256
```

## File layout (server)

```
/var/www/html/
  current_vpn_ip.txt          <- current OpenVPN server IP
  ip_scan_off.txt             <- "1" disables IP polling on routers
  port_scan_off.txt           <- "1" disables port polling on routers
  router/
    update_script.sh          <- worker script served to routers
    domain_list.txt           <- list of domains
    domain_list.txt.sha256    <- sha256 of domain_list.txt
/var/lib/remote_refresh/
  history.log                 <- IP-change history
  venv/                       <- Python virtualenv
/etc/remote-refresh.env       <- secrets + paths (not committed)
/opt/remote_refresh/          <- git clone of this repository
```

## Security notes

- The bot runs as the non-privileged `remoterefresh` user.
- `ProtectSystem=full` and `NoNewPrivileges=true` are set in the systemd unit.
- The webroot `router/` directory and IP file are writable only by `remoterefresh`.
- No secrets are committed to this repository. All credentials live in `/etc/remote-refresh.env`.
- The `domain_list.txt.sha256` prevents a network attacker from injecting hostile domains into router caches.
- The connected-check gate in `update_script.sh` eliminates the cleartext polling fingerprint while the tunnel is healthy.
