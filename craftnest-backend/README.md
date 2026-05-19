# CraftNest Backend API

Backend API services for the CraftNest marketplace. Built with FastAPI, SQLAlchemy 2.0, PostgreSQL, and Pydantic v2.

## Project Structure

```text
craftnest-backend/
├── app/
│   ├── __init__.py
│   ├── main.py             # FastAPI entry point
│   ├── core/               # config, security, db connection
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── security.py
│   │   ├── database.py
│   │   └── logging.py
│   ├── models/             # SQLAlchemy ORM models
│   │   └── __init__.py
│   ├── schemas/            # Pydantic request/response schemas
│   │   └── __init__.py
│   ├── routers/            # API endpoints grouped by topic
│   │   └── __init__.py
│   ├── services/           # business logic
│   │   └── __init__.py
│   └── utils/              # helpers
│       └── __init__.py
├── tests/
│   └── __init__.py
├── alembic/                # database migrations (init later)
├── .env.example            # template for env vars (committed)
├── .env                    # actual secrets (NOT committed)
├── .gitignore
├── pyproject.toml          # project metadata + dependencies
├── README.md
└── requirements.txt
```

## Getting Started

### 1. Prerequisites
- Python 3.12+

### 2. Local Environment Setup

1. **Activate Virtual Environment**:
   - **Windows** (PowerShell):
     ```powershell
     .venv\Scripts\Activate.ps1
     ```
   - **Windows** (CMD):
     ```cmd
     .venv\Scripts\activate.bat
     ```
   - **macOS/Linux**:
     ```bash
     source .venv/bin/activate
     ```

2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables**:
   Copy `.env.example` to `.env` if not already done:
   ```bash
   cp .env.example .env
   ```
   *Note: Edit `.env` to configure your database connection and security parameters.*

### 3. Running the Server
To run the server in hot-reload mode with HTTPS, use the helper scripts:

- **Windows**:
  ```powershell
  .\run_dev.ps1
  ```
- **macOS/Linux**:
  ```bash
  ./run_dev.sh
  ```

Run `./run_dev.sh` to start the dev server at https://localhost:8443

- **Health Check**: [https://localhost:8443/health](https://localhost:8443/health)
- **Interactive Documentation**: [https://localhost:8443/docs](https://localhost:8443/docs)
- **Alternative Documentation**: [https://localhost:8443/redoc](https://localhost:8443/redoc)

### 4. Running Tests
To execute tests using Pytest:
```bash
pytest
```

## Database Security and Roles Note

The application runs using a restricted database user `craftnest_app`.
- **Permissions**: `craftnest_app` has `CONNECT` permissions to the `craftnest` database, `USAGE` on the `public` schema, and `SELECT`, `INSERT`, `UPDATE`, `DELETE` privileges on all tables (including tables created in the future via default privileges).
- **Security Constraint**: `craftnest_app` has no schema creation or alteration permissions (`CREATE`, `ALTER`, `DROP`). Because of this, **future database migrations must be run by either the `postgres` superuser or a dedicated migrations user** with higher privileges, rather than the standard app user.

## Operations / Backups

CraftNest features a robust, automated multi-tier backup system designed to safeguard our production data.

### 1. Backup Configurations
Place the following variables inside your `.env` configuration file (do NOT commit secrets to Git):
```ini
# Operations / Backups
BACKUP_LOCAL_DIR="D:\craftnest_backups" # Path to your external SSD or local backup directory
BACKUP_GPG_PASSPHRASE="your-secure-passphrase-to-encrypt-cloud-backups"
```

> [!IMPORTANT]
> Keep the GPG passphrase stored securely in a master Password Manager. The GPG passphrase must never be logged or hardcoded.

---

### 2. Backup Tiers

#### Tier 1: Daily Local Backup (`scripts/backup_local.ps1`)
- **Process**: Employs `pg_dump` with custom binary formatting (`--format=custom`) to create compressed binary dumps.
- **Compression**: Deploys Python's native `gzip` module to compress the dump to `.dump.gz`.
- **Retention**: Preserves the last **14 daily backups**, deleting older iterations.
- **Verification**: Executes `pg_restore --list` against the raw dump to verify restorable integrity before compression; if verification fails, an alert is logged and old backups are preserved.
- **Safe Execution**: Skips silently and logs `skipped, drive missing` to `scripts/backup.log` if the external SSD path (`BACKUP_LOCAL_DIR`) is unmounted or missing.

#### Tier 2: Weekly Cloud Backup (`scripts/backup_cloud.ps1`)
- **Process**: Executes the daily local backup script first, then encrypts the latest dump using GPG (`AES256` symmetric algorithm).
- **Upload**: Uploads the encrypted payload to the cloud utilizing `rclone` (remotes must be preconfigured).
- **Retention**: Preserves the last **8 weekly backups** inside the cloud storage bucket.
- **Graceful Failover**: Gracefully logs warnings and bypasses encryption/cloud uploads if GPG or rclone are not installed, making the script safe in any local environment.

---

### 3. Setup and Installation

#### Installing Gpg4win & Rclone (Windows)
1. **GPG**: Install **Gpg4win** from [https://gpg4win.org](https://gpg4win.org). Add `C:\Program Files (x86)\GnuPG\bin\` or `C:\Program Files\GnuPG\bin\` to your System Environment variables PATH.
2. **Rclone**: Install **Rclone** from [https://rclone.org](https://rclone.org) (or run `winget install rclone`). Add `rclone.exe` to your PATH.
3. **Rclone Configuration**:
   - Run `rclone config` in your terminal.
   - Choose `n` for a new remote and name it `craftnest-backup`.
   - Select your storage provider (e.g., S3, Google Cloud Storage, B2, etc.) and complete credential inputs.

---

### 4. Scheduling Tasks

#### Windows (Task Scheduler XMLs)
Import the pre-configured Task XMLs located in `scripts/tasks/` using the Task Scheduler GUI or command line:
1. Open an **Administrator PowerShell** session.
2. Register the daily backup task (runs daily at 2:00 AM):
   ```powershell
   schtasks /create /tn "CraftNestDailyBackup" /xml "C:\Users\ACER\OneDrive\Desktop\antigravity_workspace\TohfaHub_project\craftnest-backend\scripts\tasks\daily_local_backup.xml" /f
   ```
3. Register the weekly cloud backup task (runs Sundays at 3:00 AM):
   ```powershell
   schtasks /create /tn "CraftNestWeeklyCloudBackup" /xml "C:\Users\ACER\OneDrive\Desktop\antigravity_workspace\TohfaHub_project\craftnest-backend\scripts\tasks\weekly_cloud_backup.xml" /f
   ```

#### macOS / Linux Scheduling
- **macOS (launchd)**: Place a launchd plist in `~/Library/LaunchAgents` configured to run `scripts/backup_local.sh` daily at 2:00 AM and `scripts/backup_cloud.sh` Sundays at 3:00 AM.
- **Linux (cron)**: Append standard cron jobs:
  ```bash
  # Daily local backup at 2:00 AM
  0 2 * * * /bin/bash /path/to/craftnest-backend/scripts/backup_local.sh
  
  # Weekly encrypted cloud backup on Sunday at 3:00 AM
  0 3 * * 0 /bin/bash /path/to/craftnest-backend/scripts/backup_cloud.sh
  ```

---

### 5. Restore Drill and Manual Restoration

#### Automated Restore Drill (`scripts/restore_drill.ps1`)
Run this script to verify that the latest backup can be decompressed, restored, and holds valid data:
```powershell
powershell -ExecutionPolicy Bypass -File scripts/restore_drill.ps1
```
The script will output `PASS` upon successful validation and drop the temporary testing database `craftnest_restore_test` when finished.

#### Manual Database Restore
To manually restore a specific backup `.dump.gz` file:
1. Decompress the gzip backup:
   ```powershell
   python -c "import gzip, shutil; f_in = gzip.open('craftnest_YYYY-MM-DD_HH-MM.dump.gz', 'rb'); f_out = open('craftnest_restore.dump', 'wb'); shutil.copyfileobj(f_in, f_out)"
   ```
2. Recreate target database (as superuser):
   ```sql
   DROP DATABASE IF EXISTS craftnest;
   CREATE DATABASE craftnest OWNER craftnest_app;
   ```
3. Restore the schema and data (as `craftnest_app` user):
   ```powershell
   pg_restore -h 127.0.0.1 -U craftnest_app -d craftnest --no-owner --no-acl craftnest_restore.dump
   ```
4. Clean up the decompressed `.dump` file when complete.

