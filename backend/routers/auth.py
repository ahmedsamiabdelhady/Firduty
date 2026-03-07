"""Admin authentication endpoints."""

import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from schemas.schemas import LoginRequest, TokenResponse
from services.auth_service import create_access_token, decode_token
from config import settings

router = APIRouter(prefix="/auth", tags=["auth"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/admin/login")


@router.post("/admin/login", response_model=TokenResponse)
def admin_login(request: LoginRequest):
    """Authenticate admin and return JWT.

    Uses secrets.compare_digest for both fields to prevent timing attacks
    that could reveal whether the username or password is wrong.
    """
    username_ok = secrets.compare_digest(request.username, settings.ADMIN_USERNAME)
    password_ok = secrets.compare_digest(request.password, settings.ADMIN_PASSWORD)

    if not (username_ok and password_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    token = create_access_token({"sub": request.username, "role": "admin"})
    return TokenResponse(access_token=token)


def get_current_admin(token: str = Depends(oauth2_scheme)):
    """Dependency: validate JWT and return admin username."""
    payload = decode_token(token)
    if not payload or payload.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return payload.get("sub")