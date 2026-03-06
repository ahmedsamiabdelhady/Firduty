"""Admin authentication endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from database import get_db
from schemas.schemas import LoginRequest, TokenResponse
from services.auth_service import create_access_token, decode_token
from config import settings

router = APIRouter(prefix="/auth", tags=["auth"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/admin/login")


@router.post("/admin/login", response_model=TokenResponse)
def admin_login(request: LoginRequest):
    """Authenticate admin and return JWT."""
    if request.username != settings.ADMIN_USERNAME or request.password != settings.ADMIN_PASSWORD:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_access_token({"sub": request.username, "role": "admin"})
    return TokenResponse(access_token=token)


def get_current_admin(token: str = Depends(oauth2_scheme)):
    """Dependency: validate JWT and return admin username."""
    payload = decode_token(token)
    if not payload or payload.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return payload.get("sub")