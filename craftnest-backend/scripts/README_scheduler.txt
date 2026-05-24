# CraftNest — Scheduling integrity_check.py at 4:00 AM Nightly
# =============================================================
#
# This file documents how to schedule scripts/integrity_check.py
# to run nightly at 04:00 on Linux/macOS (cron / launchd) and
# on Windows (Task Scheduler).
#
# ─────────────────────────────────────────────────────────────
# Option A: Linux cron
# ─────────────────────────────────────────────────────────────
# Add this line via `crontab -e`:
#
#   0 4 * * * /path/to/craftnest-backend/.venv/bin/python \
#       /path/to/craftnest-backend/scripts/integrity_check.py \
#       >> /var/log/craftnest_integrity.log 2>&1
#
# Replace /path/to/craftnest-backend with the real project path.
# Make sure the .env file is readable from cron's environment or
# set DATABASE_URL explicitly:
#
#   0 4 * * * DATABASE_URL="postgresql+psycopg://..." \
#       /path/to/.venv/bin/python \
#       /path/to/scripts/integrity_check.py \
#       >> /var/log/craftnest_integrity.log 2>&1
#
# ─────────────────────────────────────────────────────────────
# Option B: macOS launchd plist
# ─────────────────────────────────────────────────────────────
# Save as ~/Library/LaunchAgents/io.craftnest.integrity.plist
# then: launchctl load ~/Library/LaunchAgents/io.craftnest.integrity.plist
#
# <?xml version="1.0" encoding="UTF-8"?>
# <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
#   "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
# <plist version="1.0">
# <dict>
#   <key>Label</key>
#   <string>io.craftnest.integrity</string>
#
#   <key>ProgramArguments</key>
#   <array>
#     <string>/path/to/.venv/bin/python</string>
#     <string>/path/to/scripts/integrity_check.py</string>
#   </array>
#
#   <key>EnvironmentVariables</key>
#   <dict>
#     <key>DATABASE_URL</key>
#     <string>postgresql+psycopg://craftnest_app:password@localhost/craftnest</string>
#   </dict>
#
#   <key>StartCalendarInterval</key>
#   <dict>
#     <key>Hour</key>   <integer>4</integer>
#     <key>Minute</key> <integer>0</integer>
#   </dict>
#
#   <key>StandardOutPath</key>
#   <string>/tmp/craftnest_integrity.log</string>
#   <key>StandardErrorPath</key>
#   <string>/tmp/craftnest_integrity_err.log</string>
#
#   <key>RunAtLoad</key>
#   <false/>
# </dict>
# </plist>
#
# ─────────────────────────────────────────────────────────────
# Option C: Windows Task Scheduler (schtasks CLI)
# ─────────────────────────────────────────────────────────────
# Run once in an elevated PowerShell:
#
#   $python  = "C:\Path\To\craftnest-backend\.venv\Scripts\python.exe"
#   $script  = "C:\Path\To\craftnest-backend\scripts\integrity_check.py"
#   $logfile = "C:\Logs\craftnest_integrity.log"
#
#   schtasks /Create /TN "CraftNest\IntegrityCheck" `
#     /TR "`"$python`" `"$script`" >> `"$logfile`" 2>&1" `
#     /SC DAILY /ST 04:00 `
#     /RU SYSTEM `
#     /F
#
# To verify:
#   schtasks /Query /TN "CraftNest\IntegrityCheck" /FO LIST
#
# To run manually:
#   schtasks /Run /TN "CraftNest\IntegrityCheck"
#
# ─────────────────────────────────────────────────────────────
# Alerting
# ─────────────────────────────────────────────────────────────
# The script exits with code 1 on any FAIL. Wire your alerting
# tool (Pagerduty, Slack webhook, email) to trigger when the
# exit code is non-zero. Example with cron + mail:
#
#   MAILTO=ops@craftnest.io
#   0 4 * * * /path/to/.venv/bin/python /path/to/scripts/integrity_check.py
#
# (cron automatically mails MAILTO when a job produces output +
#  exits non-zero.)
