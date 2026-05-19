# backup_local.ps1
# Automatic daily local backup script for CraftNest PostgreSQL database on Windows

# Force UTF-8 encoding for stdout
$OutputEncoding = [System.Text.Encoding]::UTF8

# 1. Load environment variables from .env
$env_path = "$PSScriptRoot\..\.env"
if (Test-Path $env_path) {
    Get-Content $env_path | Foreach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#")) {
            $parts = $line.Split("=", 2)
            if ($parts.Count -eq 2) {
                $key = $parts[0].Trim()
                $value = $parts[1].Trim().Trim('"').Trim("'")
                [System.Environment]::SetEnvironmentVariable($key, $value)
            }
        }
    }
}

$log_file = "$PSScriptRoot\backup.log"
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

# 2. Check if BACKUP_LOCAL_DIR env is set
if (-not $env:BACKUP_LOCAL_DIR) {
    Add-Content -Path $log_file -Value "$timestamp [ERROR] BACKUP_LOCAL_DIR environment variable is not set."
    Write-Error "BACKUP_LOCAL_DIR environment variable is not set."
    Exit 1
}

# 3. Check if the backup drive/path is missing (external SSD unmounted check)
if (-not (Test-Path $env:BACKUP_LOCAL_DIR)) {
    # If the path is not a drive or if it does not exist, log skipped, drive missing instead of failing
    Add-Content -Path $log_file -Value "$timestamp [SKIP] skipped, drive missing"
    Write-Output "Backup skipped, drive missing: $env:BACKUP_LOCAL_DIR"
    Exit 0
}

# Create backup directory if it exists but needs directories inside it
if (-not (Test-Path $env:BACKUP_LOCAL_DIR -PathType Container)) {
    New-Item -ItemType Directory -Force -Path $env:BACKUP_LOCAL_DIR | Out-Null
}

# 4. Extract credentials from DATABASE_URL
if ($env:DATABASE_URL -match "postgresql\+psycopg://(?<user>[^:]+):(?<pass>[^@]+)@(?<host>[^:/]+)(:(?<port>\d+))?/(?<db>.+)") {
    $db_user = $Matches['user']
    $db_pass = $Matches['pass']
    $db_host = $Matches['host']
    $db_port = $Matches['port']
    if (-not $db_port) { $db_port = "5432" }
    $db_name = $Matches['db']
} else {
    Add-Content -Path $log_file -Value "$timestamp [ERROR] Failed to parse DATABASE_URL from .env"
    Write-Error "Failed to parse DATABASE_URL from .env"
    Exit 1
}

# Define pg_dump and pg_restore executable paths
$pg_dump_path = "C:\Program Files\PostgreSQL\17\bin\pg_dump.exe"
$pg_restore_path = "C:\Program Files\PostgreSQL\17\bin\pg_restore.exe"

if (-not (Test-Path $pg_dump_path)) {
    Add-Content -Path $log_file -Value "$timestamp [ERROR] pg_dump not found at $pg_dump_path"
    Write-Error "pg_dump not found."
    Exit 1
}

# Set file name YYYY-MM-DD_HH-MM format
$date_str = Get-Date -Format "yyyy-MM-dd_HH-mm"
$backup_filename = "craftnest_$date_str.dump"
$backup_filepath = Join-Path $env:BACKUP_LOCAL_DIR $backup_filename

# 5. Run pg_dump to produce custom binary format
$env:PGPASSWORD = $db_pass
$process_args = @(
    "-h", $db_host,
    "-p", $db_port,
    "-U", $db_user,
    "--format=custom",
    "--no-owner",
    "--no-acl",
    "-f", $backup_filepath,
    $db_name
)

Write-Output "Starting database dump to $backup_filepath..."
& $pg_dump_path @process_args

if ($LASTEXITCODE -ne 0) {
    Add-Content -Path $log_file -Value "$timestamp [ERROR] pg_dump failed with exit code $LASTEXITCODE"
    Write-Error "Database dump failed."
    Exit 1
}

# 6. Verify database dump is restorable using pg_restore --list
Write-Output "Verifying backup restorable state..."
& $pg_restore_path --list $backup_filepath | Out-Null

if ($LASTEXITCODE -ne 0) {
    Add-Content -Path $log_file -Value "$timestamp [ALERT] Backup verification failed for $backup_filename! Keeping older backups."
    Write-Error "Backup verification failed. Older backups will be preserved."
    Exit 1
}

# 7. Compress dump using Python (built-in, cross-platform, highly reliable)
$compressed_filepath = "$backup_filepath.gz"
Write-Output "Compressing dump to $compressed_filepath..."
$gzip_cmd = "import gzip, shutil; f_in = open(r'$backup_filepath', 'rb'); f_out = gzip.open(r'$compressed_filepath', 'wb'); shutil.copyfileobj(f_in, f_out); f_in.close(); f_out.close()"
& python -c $gzip_cmd

if ($LASTEXITCODE -eq 0) {
    # Remove raw dump on successful compression
    Remove-Item -Path $backup_filepath -Force
    Add-Content -Path $log_file -Value "$timestamp [SUCCESS] Local daily backup completed: $(Split-Path $compressed_filepath -Leaf)"
    Write-Output "Backup completed successfully!"
} else {
    Add-Content -Path $log_file -Value "$timestamp [ERROR] Compression failed for $backup_filename"
    Write-Error "Compression failed."
    Exit 1
}

# 8. Keep only the last 14 daily backups, delete older ones
$backups = Get-ChildItem -Path $env:BACKUP_LOCAL_DIR -Filter "craftnest_*.dump.gz" | Sort-Object Name -Descending
if ($backups.Count -gt 14) {
    $old_backups = $backups[14..($backups.Count - 1)]
    foreach ($old_backup in $old_backups) {
        Remove-Item -Path $old_backup.FullName -Force
        Add-Content -Path $log_file -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [CLEANUP] Deleted old local backup: $($old_backup.Name)"
        Write-Output "Cleaned up old local backup: $($old_backup.Name)"
    }
}
