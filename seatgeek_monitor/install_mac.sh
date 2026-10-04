#!/bin/bash
# Installs the monitor as a macOS LaunchAgent: starts at login, restarts if it crashes.
# Uninstall: ./install_mac.sh uninstall
set -e
LABEL=com.user.seatgeek-monitor
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
DIR="$(cd "$(dirname "$0")" && pwd)"

if [ "$1" = "uninstall" ]; then
  launchctl unload "$PLIST" 2>/dev/null || true
  rm -f "$PLIST"; echo "Uninstalled."; exit 0
fi

PY="$(command -v python3)"
"$PY" -m pip install --user -q playwright
"$PY" -m playwright install chromium

mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<P
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array>
    <string>$PY</string><string>-u</string><string>$DIR/monitor.py</string>
  </array>
  <key>WorkingDirectory</key><string>$DIR</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>
  <key>StandardOutPath</key><string>$DIR/monitor.log</string>
  <key>StandardErrorPath</key><string>$DIR/monitor.log</string>
</dict></plist>
P
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "Installed. Running a test check now..."
"$PY" "$DIR/monitor.py" --dump
echo "Background monitor is running. Log: $DIR/monitor.log"
