"""Request dependencies: DB session, authenticated user, role guards."""

import uuid
from collections.abc import Callable
from typing import Annotated

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .database import get_db
from .errors import Forbidden, Unauthorized
from .models import STAFF_ROLES, User, UserRole
from .services.security import decode_access_token

bearer = HTTPBearer(auto_error=False, description="Paste the accessToken from POST /api/v1/auth/login")

DB = Annotated[Session, Depends(get_db)]


def get_authenticated_user(db: DB, creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> User:
    """Any signed-in user, staff or karigar. Only /auth/me and /portal/* accept karigar logins."""
    if creds is None or creds.scheme.lower() != "bearer":
        raise Unauthorized("Authentication required")
    try:
        payload = decode_access_token(creds.credentials)
        user_id = uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise Unauthorized("Invalid or expired token", code="invalid_token")
    user = db.get(User, user_id)
    if user is None or not user.is_active or str(user.organisation_id) != payload.get("org"):
        raise Unauthorized("Account is inactive or no longer exists", code="invalid_token")
    return user


AnyUser = Annotated[User, Depends(get_authenticated_user)]


def get_current_user(user: AnyUser) -> User:
    """Jeweller staff only. Deny-by-default for karigar logins: a karigar can never reach an
    organisation-wide endpoint, only their own account through /portal."""
    if user.role not in STAFF_ROLES:
        raise Forbidden("Karigar accounts can only use the karigar portal", code="staff_only")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_karigar_user(user: AnyUser) -> User:
    if user.role != UserRole.karigar or user.karigar_id is None:
        raise Forbidden("This endpoint is for karigar accounts", code="karigar_only")
    return user


KarigarUser = Annotated[User, Depends(get_karigar_user)]


def require_roles(*roles: UserRole) -> Callable[[User], User]:
    allowed = set(roles)

    def _check(user: CurrentUser) -> User:
        if user.role not in allowed:
            raise Forbidden(f"Your role ({user.role}) cannot perform this action", details={"requiredRoles": sorted(r.value for r in allowed)})
        return user

    return _check


# Permission matrix (see docs/API.md)
ADMIN = (UserRole.admin,)
MANAGE = (UserRole.admin, UserRole.manager)  # karigars, jobs, reversals, user/audit read
VAULT_OPS = (UserRole.admin, UserRole.manager, UserRole.vault_operator)  # lots, issue, acknowledge

Admin = Annotated[User, Depends(require_roles(*ADMIN))]
Manager = Annotated[User, Depends(require_roles(*MANAGE))]
VaultOperator = Annotated[User, Depends(require_roles(*VAULT_OPS))]
