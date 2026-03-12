"""
routers/auth.py — Admin authentication endpoints.

Two login routes are provided to support every client without breaking any:

  POST /auth/admin/login           — OAuth2 form body (application/x-www-form-urlencoded)
                                     Used by Swagger UI "Authorize" button.
                                     Required for FastAPI OAuth2PasswordBearer to work.

  POST /auth/admin/login/json      — JSON body  (application/json)
                                     Used by the Admin Web UI (login.js) and any
                                     HTTP client that prefers JSON.

Both routes check the same credentials and return the same TokenResponse.

  GET  /auth/validate              — Returns the current admin identity.
                                     Useful for Admin UI to verify a stored token
                                     is still valid without making a business call.
"""

import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

from schemas.schemas import LoginRequest, TokenResponse, AdminIdentity
from services.auth_service import create_access_token, decode_token
from config import settings

router = APIRouter(prefix="/auth", tags=["auth"])

# tokenUrl must match the FORM-based login route exactly so Swagger Authorize works.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/admin/login")


# ── Shared login logic ────────────────────────────────────────────────────────

def _verify_and_issue(username: str, password: str) -> TokenResponse:
    """
    Validate admin credentials (timing-safe) and issue a JWT.
    Raises HTTP 401 on failure.
    """
    username_ok = secrets.compare_digest(username, settings.ADMIN_USERNAME)
    password_ok = secrets.compare_digest(password, settings.ADMIN_PASSWORD)

    if not (username_ok and password_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token({"sub": username, "role": "admin"})
    return TokenResponse(access_token=token)


# ── Login — OAuth2 form body (Swagger Authorize) ──────────────────────────────

@router.post(
    "/admin/login",
    response_model=TokenResponse,
    summary="Admin login (Swagger / OAuth2 form)",
    description=(
        "Accepts `application/x-www-form-urlencoded` with `username` and `password` fields. "
        "This is the endpoint used by the Swagger UI **Authorize** button."
    ),
)
def admin_login_form(form_data: OAuth2PasswordRequestForm = Depends()):
    """OAuth2 password flow — used by Swagger UI Authorize and any form-based client."""
    return _verify_and_issue(form_data.username, form_data.password)


# ── Login — JSON body (Admin Web UI / direct API calls) ───────────────────────

@router.post(
    "/admin/login/json",
    response_model=TokenResponse,
    summary="Admin login (JSON body)",
    description=(
        "Accepts `application/json` with `{username, password}`. "
        "Used by the Admin Web UI (login.js) and any JSON API client."
    ),
)
def admin_login_json(request: LoginRequest):
    """JSON login — used by the Admin Web UI and programmatic API clients."""
    return _verify_and_issue(request.username, request.password)


# ── Token validation ──────────────────────────────────────────────────────────

@router.get(
    "/validate",
    response_model=AdminIdentity,
    summary="Validate token and return admin identity",
    description=(
        "Confirms the Authorization Bearer token is valid and not expired. "
        "Returns admin username and token expiry. "
        "Used by the Admin Web UI to check session state on page load."
    ),
)
def validate_token(token: str = Depends(oauth2_scheme)):
    """Return admin identity if token is valid; 401 otherwise."""
    payload = decode_token(token)
    if not payload or payload.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return AdminIdentity(
        username=str(payload.get("sub", "")),
        role="admin",
        expires_at=payload.get("exp"),
    )


# ── Auth dependency (imported by all other routers) ───────────────────────────

def get_current_admin(token: str = Depends(oauth2_scheme)) -> str:
    """
    FastAPI dependency — validate JWT and return admin username.

    Usage in any protected router:
        admin = Depends(get_current_admin)

    Raises HTTP 401 if token is missing, invalid, or expired.
    Raises HTTP 403 if token is valid but the role is not 'admin'.
    """
    payload = decode_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if payload.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return str(sub)