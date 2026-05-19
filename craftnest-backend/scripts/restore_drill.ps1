# restore_drill.ps1
# Database restore drill verification script for CraftNest on Windows

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

# Parse DATABASE_URL
if ($env:DATABASE_URL -match "postgresql\+psycopg://(?<user>[^:]+):(?<pass>[^@]+)@(?<host>[^:/]+)(:(?<port>\d+))?/(?<db>.+)") {
    $db_user = $Matches['user']
    $db_pass = $Matches['pass']
    $db_host = $Matches['host']
    $db_port = $Matches['port']
    if (-not $db_port) { $db_port = "5432" }
    $db_name = $Matches['db']
} else {
    Write-Output "FAIL: Failed to parse DATABASE_URL from .env"
    Exit 1
}

# 2. Find the latest backup
if (-not $env:BACKUP_LOCAL_DIR -or -not (Test-Path $env:BACKUP_LOCAL_DIR)) {
    Write-Output "FAIL: BACKUP_LOCAL_DIR is not configured or missing."
    Exit 1
}

$latest_backup = Get-ChildItem -Path $env:BACKUP_LOCAL_DIR -Filter "craftnest_*.dump.gz" | Sort-Object Name -Descending | Select-Object -First 1
if (-not $latest_backup) {
    Write-Output "FAIL: No backup files found in $env:BACKUP_LOCAL_DIR"
    Exit 1
}

Write-Output "Latest backup found: $($latest_backup.Name)"

# 3. Decompress to a temp .dump file using Python
$temp_dump_path = Join-Path $PSScriptRoot "temp_restore.dump"
Write-Output "Decompressing backup..."
$decomp_cmd = "import gzip, shutil; f_in = gzip.open(r'$($latest_backup.FullName)', 'rb'); f_out = open(r'$temp_dump_path', 'wb'); shutil.copyfileobj(f_in, f_out); f_in.close(); f_out.close()"
& python -c $decomp_cmd

if ($LASTEXITCODE -ne 0 -or -not (Test-Path $temp_dump_path)) {
    Write-Output "FAIL: Decompression failed."
    Exit 1
}

# Executable paths
$psql_path = "C:\Program Files\PostgreSQL\17\bin\psql.exe"
$pg_restore_path = "C:\Program Files\PostgreSQL\17\bin\pg_restore.exe"

# 4. Create the separate DB craftnest_restore_test using superuser
Write-Output "Creating clean test restore database craftnest_restore_test..."
$env:PGPASSWORD = "13inches"
& $psql_path -h 127.0.0.1 -U postgres -d postgres -c "DROP DATABASE IF EXISTS craftnest_restore_test;" | Out-Null
& $psql_path -h 127.0.0.1 -U postgres -d postgres -c "CREATE DATABASE craftnest_restore_test OWNER craftnest_app;" | Out-Null

if ($LASTEXITCODE -ne 0) {
    Write-Output "FAIL: Failed to recreate database craftnest_restore_test."
    if (Test-Path $temp_dump_path) { Remove-Item -Path $temp_dump_path -Force }
    Exit 1
}

# Grant public schema permissions to restore DB so pg_restore doesn't throw privileges errors
& $psql_path -h 127.0.0.1 -U postgres -d craftnest_restore_test -c "GRANT ALL ON SCHEMA public TO craftnest_app; ALTER SCHEMA public OWNER TO craftnest_app;" | Out-Null

# 5. Restore using pg_restore with craftnest_app credentials
Write-Output "Restoring dump into craftnest_restore_test..."
$env:PGPASSWORD = $db_pass
$restore_args = @(
    "-h", $db_host,
    "-p", $db_port,
    "-U", $db_user,
    "-d", "craftnest_restore_test",
    "--no-owner",
    "--no-acl",
    $temp_dump_path
)
& $pg_restore_path @restore_args 2>&1 | Out-Null

# 6. Verify row count to confirm tables and rows are restored successfully
Write-Output "Checking row counts in users and items tables..."
$users_count = & $psql_path -h $db_host -p $db_port -U $db_user -d "craftnest_restore_test" -t -A -c "SELECT COUNT(*) FROM users;"
$items_count = & $psql_path -h $db_host -p $db_port -U $db_user -d "craftnest_restore_test" -t -A -c "SELECT COUNT(*) FROM items;"

Write-Output "Restored database counts -> Users: $users_count, Items: $items_count"

# Check counts
if ([int]$users_count -gt 0 -and [int]$items_count -gt 0) {
    Write-Output "PASS"
} else {
    Write-Output "FAIL: Restore succeeded but table counts are zero."
}

# 7. Cleanup temp files and drop database
Write-Output "Cleaning up temporary files and dropping restore test DB..."
if (Test-Path $temp_dump_path) {
    Remove-Item -Path $temp_dump_path -Force
}

$env:PGPASSWORD = "13inches"
& $psql_path -h 127.0.0.1 -U postgres -d postgres -c "DROP DATABASE IF EXISTS craftnest_restore_test;" | Out-Null
