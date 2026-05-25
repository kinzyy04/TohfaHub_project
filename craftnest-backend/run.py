import sys
import asyncio

# Set the selector event loop policy on Windows for psycopg async compatibility
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import os
import uvicorn
from app.main import app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8443))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
