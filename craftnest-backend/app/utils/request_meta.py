from fastapi import Request

def extract_request_meta(request: Request | None) -> tuple[str | None, str | None]:
    """Extracts the client IP address and user-agent string from the FastAPI Request object."""
    if not request:
        return None, None
        
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    
    return ip_address, user_agent
