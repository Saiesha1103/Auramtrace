from fastapi import APIRouter, status
from sqlalchemy import func, select

from ..config import get_settings
from ..deps import DB, CurrentUser
from ..errors import Conflict, Forbidden, Unauthorized
from ..models import Organisation, User, UserRole
from ..schemas import ERROR_RESPONSES, LoginRequest, RegisterRequest, TokenResponse, UserOut
from ..services import audit
from ..services.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["Auth"], responses=ERROR_RESPONSES)


def _token(user: User) -> TokenResponse:
    token, expires_in = create_access_token(user.id, user.organisation_id, user.role.value)
    return TokenResponse(access_token=token, expires_in=expires_in, user=UserOut.model_validate(user))


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED, summary="Create an organisation and its first admin")
def register(body: RegisterRequest, db: DB) -> TokenResponse:
    """Self-service bootstrap. Disabled when `AURUM_ALLOW_REGISTRATION=false` (required in production)."""
    if not get_settings().allow_registration:
        raise Forbidden("Self-service registration is disabled", code="registration_disabled")
    email = body.email.lower()
    if db.scalar(select(func.count()).select_from(User).where(func.lower(User.email) == email)):
        raise Conflict("An account with this email already exists", code="email_taken")
    org = Organisation(name=body.organisation_name.strip())
    db.add(org)
    db.flush()
    user = User(organisation_id=org.id, email=email, full_name=body.full_name.strip(), role=UserRole.admin, password_hash=hash_password(body.password))
    db.add(user)
    db.flush()
    audit.record(db, user, org.id, "organisation.registered", "organisation", org.id, {"name": org.name, "adminEmail": email})
    db.commit()
    return _token(user)


@router.post("/login", response_model=TokenResponse, summary="Exchange email + password for a bearer token")
def login(body: LoginRequest, db: DB) -> TokenResponse:
    user = db.scalar(select(User).where(func.lower(User.email) == body.email.lower()))
    if user is None or not verify_password(body.password, user.password_hash):
        raise Unauthorized("Incorrect email or password", code="invalid_credentials")
    if not user.is_active:
        raise Unauthorized("This account is deactivated", code="account_inactive")
    return _token(user)


@router.get("/me", response_model=UserOut, summary="The signed-in user")
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
