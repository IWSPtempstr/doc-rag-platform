from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import MembershipModel, UserModel, WorkspaceModel
from app.routers.auth import require_admin_role


def _db_session(role: str):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add(WorkspaceModel(id=1, name="A股研究", slug="ashare"))
    db.add(UserModel(id=1, email="u@example.com", name="User", password_hash="x"))
    db.add(MembershipModel(user_id=1, workspace_id=1, role=role))
    db.commit()
    return db


def test_admin_role_can_access_admin_area():
    db = _db_session("admin")
    user = db.query(UserModel).first()

    membership = require_admin_role(db, user.id, workspace_id=1)

    assert membership.role == "admin"


def test_user_role_cannot_access_admin_area():
    db = _db_session("user")
    user = db.query(UserModel).first()

    try:
        require_admin_role(db, user.id, workspace_id=1)
    except HTTPException as exc:
        assert exc.status_code == 403
        assert "管理员" in str(exc.detail)
    else:
        raise AssertionError("user role must not access admin area")
