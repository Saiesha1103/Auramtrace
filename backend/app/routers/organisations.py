import uuid

from fastapi import APIRouter, Query, status
from sqlalchemy import func, select

from ..deps import DB, Admin, CurrentUser, Manager
from ..errors import BusinessRuleViolation, Conflict, NotFound
from ..models import AuditEvent, Organisation, User, UserRole
from ..schemas import ERROR_RESPONSES, AuditOut, OrganisationOut, OrganisationUpdate, Page, UserCreate, UserOut, UserUpdate
from ..services import audit
from ..services.security import hash_password

router = APIRouter(tags=["Organisation & users"], responses=ERROR_RESPONSES)


@router.get("/organisations/me", response_model=OrganisationOut, summary="Your organisation")
def get_org(user: CurrentUser, db: DB) -> OrganisationOut:
    return OrganisationOut.model_validate(db.get(Organisation, user.organisation_id))


@router.patch("/organisations/me", response_model=OrganisationOut, summary="Rename your organisation (admin)")
def update_org(body: OrganisationUpdate, user: Admin, db: DB) -> OrganisationOut:
    org = db.get(Organisation, user.organisation_id)
    before = org.name
    org.name = body.name.strip()
    audit.record(db, user, org.id, "organisation.updated", "organisation", org.id, {"name": {"from": before, "to": org.name}})
    db.commit()
    return OrganisationOut.model_validate(org)


@router.get("/users", response_model=Page[UserOut], summary="List users in your organisation (admin, manager)")
def list_users(user: Manager, db: DB, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)) -> Page[UserOut]:
    q = select(User).where(User.organisation_id == user.organisation_id)
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = db.scalars(q.order_by(User.created_at).limit(limit).offset(offset))
    return Page(items=[UserOut.model_validate(u) for u in rows], total=total, limit=limit, offset=offset)


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED, summary="Add a user to your organisation (admin)")
def create_user(body: UserCreate, user: Admin, db: DB) -> UserOut:
    email = body.email.lower()
    if db.scalar(select(func.count()).select_from(User).where(func.lower(User.email) == email)):
        raise Conflict("An account with this email already exists", code="email_taken")
    new = User(organisation_id=user.organisation_id, email=email, full_name=body.full_name.strip(), role=body.role, password_hash=hash_password(body.password))
    db.add(new)
    db.flush()
    audit.record(db, user, user.organisation_id, "user.created", "user", new.id, {"email": email, "role": body.role})
    db.commit()
    return UserOut.model_validate(new)


@router.patch("/users/{user_id}", response_model=UserOut, summary="Change a user's name, role or active flag (admin)")
def update_user(user_id: uuid.UUID, body: UserUpdate, user: Admin, db: DB) -> UserOut:
    target = db.get(User, user_id)
    if target is None or target.organisation_id != user.organisation_id:
        raise NotFound("User not found")
    changes = body.model_dump(exclude_unset=True)
    if target.id == user.id and (changes.get("role", UserRole.admin) != UserRole.admin or changes.get("is_active") is False):
        raise BusinessRuleViolation("You cannot demote or deactivate your own account", code="self_lockout")
    diff = {}
    if "password" in changes and changes["password"]:
        new_pw = changes.pop("password")
        target.password_hash = hash_password(new_pw)
        diff["password"] = {"from": "***", "to": "***"}
    for k, v in changes.items():
        if v is not None and getattr(target, k) != v:
            diff[k] = {"from": getattr(target, k), "to": v}
            setattr(target, k, v)
    if diff:
        audit.record(db, user, user.organisation_id, "user.updated", "user", target.id, diff)
    db.commit()
    return UserOut.model_validate(target)


@router.get("/audit", response_model=Page[AuditOut], summary="Audit trail, newest first (admin, manager)")
def list_audit(
    user: Manager,
    db: DB,
    entity_type: str | None = Query(None, alias="entityType"),
    entity_id: str | None = Query(None, alias="entityId"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> Page[AuditOut]:
    q = select(AuditEvent).where(AuditEvent.organisation_id == user.organisation_id)
    if entity_type:
        q = q.where(AuditEvent.entity_type == entity_type)
    if entity_id:
        q = q.where(AuditEvent.entity_id == entity_id)
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = list(db.scalars(q.order_by(AuditEvent.created_at.desc()).limit(limit).offset(offset)))
    names = {u.id: u.full_name for u in db.scalars(select(User).where(User.id.in_({r.actor_user_id for r in rows if r.actor_user_id})))}
    items = [AuditOut(id=r.id, actor_user_id=r.actor_user_id, actor_name=names.get(r.actor_user_id), action=r.action, entity_type=r.entity_type, entity_id=r.entity_id, details=r.details, created_at=r.created_at) for r in rows]
    return Page(items=items, total=total, limit=limit, offset=offset)
