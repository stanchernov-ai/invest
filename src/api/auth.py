import os
import logging
import azure.functions as func
from typing import Callable, Any
from functools import wraps

try:
    import jwt
    from jwt import PyJWKClient
except ImportError:
    jwt = None
    PyJWKClient = None

logger = logging.getLogger(__name__)

ENTRA_TENANT_ID = os.environ.get("ENTRA_TENANT_ID")
ENTRA_CLIENT_ID = os.environ.get("ENTRA_CLIENT_ID")
JWKS_URL = f"https://login.microsoftonline.com/{ENTRA_TENANT_ID}/discovery/v2.0/keys"

if ENTRA_TENANT_ID:
    jwks_client = PyJWKClient(JWKS_URL)
else:
    jwks_client = None

def require_auth(f: Callable) -> Callable:
    """Decorator to validate Entra JWTs and extract the entra_oid to map to a user_id."""
    @wraps(f)
    async def wrapper(req: func.HttpRequest, *args, **kwargs):
        # Allow bypass for local dev if ENTRA_TENANT_ID is not set
        if not ENTRA_TENANT_ID:
            # Default to Stan for local dev without auth
            req.user_id = "stan" 
            return await f(req, *args, **kwargs)

        auth_header = req.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return func.HttpResponse("Missing or invalid Authorization header", status_code=401)
        
        token = auth_header.split(" ")[1]

        try:
            signing_key = jwks_client.get_signing_key_from_jwt(token)
            data = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=ENTRA_CLIENT_ID,
                issuer=f"https://sts.windows.net/{ENTRA_TENANT_ID}/"
            )
            
            entra_oid = data.get("oid")
            if not entra_oid:
                return func.HttpResponse("Token missing oid claim", status_code=401)
            
            # Map entra_oid to Postgres user_id
            from src.data.db import fetch_row
            row = await fetch_row("SELECT id FROM users WHERE entra_oid = $1 AND status = 'active'", entra_oid)
            
            if not row:
                return func.HttpResponse("User not found or inactive", status_code=403)
                
            # Attach user_id to the request object for the route to use
            req.user_id = str(row['id'])
            
            return await f(req, *args, **kwargs)
            
        except Exception as e:
            logger.error(f"JWT Validation failed: {e}")
            return func.HttpResponse("Invalid Token", status_code=401)

    return wrapper
