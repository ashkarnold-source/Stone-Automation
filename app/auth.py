import secrets
import os
from fastapi import Request
from fastapi.responses import Response


async def basic_auth_middleware(request: Request, call_next):
    # Skip auth for health check (Railway uses this to verify the app is running)
    if request.url.path == "/health":
        return await call_next(request)

    expected_user = os.getenv("ADMIN_USERNAME", "")
    expected_pass = os.getenv("ADMIN_PASSWORD", "")

    if not expected_user or not expected_pass:
        return Response(
            "ADMIN_USERNAME and ADMIN_PASSWORD must be set in environment variables.",
            status_code=500,
        )

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Basic "):
        import base64
        try:
            decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
            username, _, password = decoded.partition(":")
            user_ok = secrets.compare_digest(username.encode(), expected_user.encode())
            pass_ok = secrets.compare_digest(password.encode(), expected_pass.encode())
            if user_ok and pass_ok:
                return await call_next(request)
        except Exception:
            pass

    return Response(
        "Authentication required.",
        status_code=401,
        headers={"WWW-Authenticate": 'Basic realm="Stone Command Center"'},
    )
