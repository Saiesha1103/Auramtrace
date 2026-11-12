import uuid

from fastapi import APIRouter, Query, status
from sqlalchemy import func, or_, select

from ..deps import DB, CurrentUser, Manager
from ..errors import BusinessRuleViolation
from ..models import Karigar, KarigarKind, KarigarStatus
from ..schemas import ERROR_RESPONSES, HierarchyNode, KarigarCreate, KarigarOut, KarigarProfile, KarigarUpdate, Page
from ..services import audit
from ..services.codes import ensure_unique_code, next_code
from ..services.custody import get_in_org
from ..services.ledger import karigar_holding
from ..services.views import karigar_profile

router = APIRouter(prefix="/karigars", tags=["Karigars"], responses=ERROR_RESPONSES)


def _validate_head(db, org_id: uuid.UUID, kind: KarigarKind, head_id: uuid.UUID | None, self_id: uuid.UUID | None = None) -> None:
    if head_id is None:
        return
    if kind == KarigarKind.head_karigar:
        raise BusinessRuleViolation("A head karigar cannot report to another head karigar", code="invalid_hierarchy")
    if self_id and head_id == self_id:
        raise BusinessRuleViolation("A karigar cannot be their own head", code="invalid_hierarchy")
    head = get_in_org(db, Karigar, org_id, head_id, "Head karigar")
    if head.kind != KarigarKind.head_karigar:
        raise BusinessRuleViolation(f"{head.code} is not a head karigar", code="invalid_hierarchy")


@router.get("", response_model=Page[KarigarOut], summary="Directory with filters")
def list_karigars(
    user: CurrentUser,
    db: DB,
    kind: KarigarKind | None = None,
    status_: KarigarStatus | None = Query(None, alias="status"),
    head_karigar_id: uuid.UUID | None = Query(None, alias="headKarigarId"),
    q: str | None = Query(None, max_length=80, description="Search code, name, unit"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> Page[KarigarOut]:
    stmt = select(Karigar).where(Karigar.organisation_id == user.organisation_id)
    if kind:
        stmt = stmt.where(Karigar.kind == kind)
    if status_:
        stmt = stmt.where(Karigar.status == status_)
    if head_karigar_id:
        stmt = stmt.where(Karigar.head_karigar_id == head_karigar_id)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(Karigar.code).like(like), func.lower(Karigar.name).like(like), func.lower(func.coalesce(Karigar.unit, "")).like(like)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(Karigar.code).limit(limit).offset(offset))
    return Page(items=[KarigarOut.model_validate(k) for k in rows], total=total, limit=limit, offset=offset)


@router.post("", response_model=KarigarOut, status_code=status.HTTP_201_CREATED, summary="Register a karigar / head karigar / subcontractor (admin, manager)")
def create_karigar(body: KarigarCreate, user: Manager, db: DB) -> KarigarOut:
    org = user.organisation_id
    _validate_head(db, org, body.kind, body.head_karigar_id)
    code = ensure_unique_code(db, Karigar, org, body.code) if body.code else next_code(db, Karigar, org, "K")
    k = Karigar(organisation_id=org, code=code, name=body.name.strip(), kind=body.kind, head_karigar_id=body.head_karigar_id, unit=body.unit, contact=body.contact, skills=body.skills)
    db.add(k)
    db.flush()
    audit.record(db, user, org, "karigar.created", "karigar", k.id, {"code": code, "name": k.name, "kind": k.kind, "headKarigarId": k.head_karigar_id})
    db.commit()
    return KarigarOut.model_validate(k)


@router.get("/hierarchy", response_model=list[HierarchyNode], summary="Head karigars with their teams, and independents, with fine gold held")
def hierarchy(user: CurrentUser, db: DB) -> list[HierarchyNode]:
    all_k = list(db.scalars(select(Karigar).where(Karigar.organisation_id == user.organisation_id).order_by(Karigar.code)))
    held = {k.id: karigar_holding(db, user.organisation_id, k.id).fine for k in all_k}

    def node(k: Karigar) -> HierarchyNode:
        kids = [c for c in all_k if c.head_karigar_id == k.id]
        return HierarchyNode(id=k.id, code=k.code, name=k.name, kind=k.kind, status=k.status, fine_gold_held_g=held[k.id], children=[node(c) for c in kids])

    return [node(k) for k in all_k if k.head_karigar_id is None]


@router.get("/{karigar_id}", response_model=KarigarProfile, summary="Profile: hierarchy, custody (derived from events), recent movements")
def get_karigar(karigar_id: uuid.UUID, user: CurrentUser, db: DB) -> KarigarProfile:
    return karigar_profile(db, get_in_org(db, Karigar, user.organisation_id, karigar_id, "Karigar"))


@router.patch("/{karigar_id}", response_model=KarigarOut, summary="Update profile fields or status (admin, manager). Custody history is unaffected.")
def update_karigar(karigar_id: uuid.UUID, body: KarigarUpdate, user: Manager, db: DB) -> KarigarOut:
    k = get_in_org(db, Karigar, user.organisation_id, karigar_id, "Karigar")
    changes = body.model_dump(exclude_unset=True)
    if "head_karigar_id" in changes:
        _validate_head(db, user.organisation_id, k.kind, changes["head_karigar_id"], k.id)
    if changes.get("status") == KarigarStatus.inactive and k.kind == KarigarKind.head_karigar:
        active_team = db.scalar(select(func.count()).select_from(Karigar).where(Karigar.head_karigar_id == k.id, Karigar.status == KarigarStatus.active))
        if active_team:
            raise BusinessRuleViolation("Reassign or deactivate this head karigar's active team first", code="has_active_team")
    diff = {}
    for key, v in changes.items():
        if key != "head_karigar_id" and v is None:
            continue
        if getattr(k, key) != v:
            diff[key] = {"from": getattr(k, key), "to": v}
            setattr(k, key, v)
    if diff:
        audit.record(db, user, user.organisation_id, "karigar.updated", "karigar", k.id, diff)
    db.commit()
    return KarigarOut.model_validate(k)
