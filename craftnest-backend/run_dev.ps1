# Activate the virtual environment
if (Test-Path ".venv\Scripts\Activate.ps1") {
    .venv\Scripts\Activate.ps1
} else {
    Write-Warning "Virtual environment not found at .venv\Scripts\Activate.ps1. Attempting to run uvicorn directly."
}

# Start uvicorn with SSL configuration
uvicorn app.main:app --reload `
    --host 127.0.0.1 --port 8443 `
    --ssl-keyfile certs/localhost-key.pem `
    --ssl-certfile certs/localhost.pem
