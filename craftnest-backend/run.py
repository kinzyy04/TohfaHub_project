import sys
import asyncio

# Set the selector event loop policy on Windows for psycopg async compatibility
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uvicorn
from app.main import app

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8443, ssl_keyfile="certs/localhost-key.pem", ssl_certfile="certs/localhost.pem", loop="none", log_level="info")
