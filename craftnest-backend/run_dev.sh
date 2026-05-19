#!/bin/bash

# Activate the virtual environment
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
elif [ -f ".venv/Scripts/activate" ]; then
    source .venv/Scripts/activate
else
    echo "Warning: Virtual environment activation script not found. Attempting to run uvicorn directly."
fi

# Start uvicorn with SSL configuration
uvicorn app.main:app --reload \
    --host 127.0.0.1 --port 8443 \
    --ssl-keyfile certs/localhost-key.pem \
    --ssl-certfile certs/localhost.pem
