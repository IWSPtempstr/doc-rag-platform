"""Authentication routes for the finance workbench."""

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.config import config
from app.db import get_db
from app.models import MembershipModel, UserModel, WorkspaceModel
from app.schemas import LoginRequest, MeResponse, UserResponse, WorkspaceResponse
from app.services.auth_service import authenticate_or_bootstrap, create_token, get_user_by_token

router = APIRouter(prefix="/api/auth", tags=["Auth"])


def get_current_user(
    token: str | None = Cookie(default=None, alias=config.AUTH_COOKIE_NAME),
    db: Session = Depends(get_db),
) -> UserModel:
    user = get_user_by_token(db, token)
    if not user:
        raise HTTPException(401, "未登录")
    return user


def get_current_workspace(
    workspace_id: int = Query(1, alias="workspace_id"),
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> tuple[UserModel, WorkspaceModel]:
    membership = (
        db.query(MembershipModel)
        .filter(
            MembershipModel.user_id == current_user.id,
            MembershipModel.workspace_id == workspace_id,
        )
        .first()
    )
    if not membership:
        raise HTTPException(403, "你没有该工作空间的访问权限")
    return current_user, membership.workspace


def require_admin_role(db: Session, user_id: int, workspace_id: int) -> MembershipModel:
    membership = (
        db.query(MembershipModel)
        .filter(MembershipModel.user_id == user_id, MembershipModel.workspace_id == workspace_id)
        .first()
    )
    if not membership:
        raise HTTPException(403, "你没有该工作空间的访问权限")
    if membership.role not in {"admin", "owner"}:
        raise HTTPException(403, "需要管理员权限")
    return membership


def get_current_admin_workspace(
    workspace_id: int = Query(1, alias="workspace_id"),
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> tuple[UserModel, WorkspaceModel]:
    membership = require_admin_role(db, current_user.id, workspace_id)
    return current_user, membership.workspace


@router.post("/login", response_model=MeResponse)
def login(req: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = authenticate_or_bootstrap(db, req.email, req.password, req.name)
    if not user:
        raise HTTPException(401, "邮箱或密码错误")

    token = create_token(user.id)
    response.set_cookie(
        key=config.AUTH_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=config.AUTH_TOKEN_TTL_SECONDS,
    )
    return _me_response(db, user.id)


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(config.AUTH_COOKIE_NAME)
    return {"ok": True}


@router.get("/me", response_model=MeResponse)
def me(
    token: str | None = Cookie(default=None, alias=config.AUTH_COOKIE_NAME),
    db: Session = Depends(get_db),
):
    user = get_user_by_token(db, token)
    if not user:
        raise HTTPException(401, "未登录")
    return _me_response(db, user.id)


def _me_response(db: Session, user_id: int) -> MeResponse:
    user = get_user_by_token(db, create_token(user_id))
    memberships = (
        db.query(MembershipModel)
        .filter(MembershipModel.user_id == user_id)
        .all()
    )
    workspaces = [m.workspace for m in memberships if m.workspace]
    return MeResponse(
        user=UserResponse.model_validate(user),
        workspaces=[
            WorkspaceResponse(
                id=m.workspace.id,
                name=m.workspace.name,
                slug=m.workspace.slug,
                created_at=m.workspace.created_at,
                role=m.role,
            )
            for m in memberships if m.workspace
        ],
    )
