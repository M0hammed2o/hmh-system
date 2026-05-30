"""Tests for project assignment enforcement on site-role users."""

import pytest
from tests.conftest import make_project, make_user
from app.models.user import User
from app.models.enums import UserRole
from app.models.access import UserProjectAccess
from app.schemas.user import UserCreate, UserUpdate
from app.services import user_service
from app.core.exceptions import ValidationError


# ── Helpers ───────────────────────────────────────────────────────────────────

SITE_ROLES = ["SITE_MANAGER", "SITE_MANAGER_VIEW", "SITE_STAFF"]
OFFICE_ROLES = ["OWNER", "OFFICE_ADMIN", "OFFICE_USER", "READ_ONLY"]


def _owner(db):
    return make_user(db, role="OWNER")


# ── create_user enforcement ────────────────────────────────────────────────────

@pytest.mark.parametrize("role", SITE_ROLES)
def test_create_site_role_without_projects_raises(db, role):
    """Creating a site role user without project_ids must raise ValidationError."""
    owner = _owner(db)
    data = UserCreate(
        full_name="Site Person",
        email=f"site_{role.lower()}@test.com",
        role=UserRole(role),
        project_ids=[],
    )
    with pytest.raises(ValidationError, match="requires at least one project assignment"):
        user_service.create_user(db, data, owner["id"])


@pytest.mark.parametrize("role", SITE_ROLES)
def test_create_site_role_with_project_succeeds(db, role):
    """Creating a site role user WITH a project_id must succeed and create access record."""
    owner = _owner(db)
    project = make_project(db, owner["id"])

    data = UserCreate(
        full_name="Site Person",
        email=f"site_{role.lower()}_ok@test.com",
        role=UserRole(role),
        project_ids=[project["id"]],
    )
    user, temp_pwd = user_service.create_user(db, data, owner["id"])
    assert user.id is not None
    assert temp_pwd

    access_records = (
        db.query(UserProjectAccess)
        .filter(UserProjectAccess.user_id == user.id)
        .all()
    )
    assert len(access_records) == 1
    assert str(access_records[0].project_id) == project["id"]
    assert access_records[0].can_view is True


@pytest.mark.parametrize("role", OFFICE_ROLES)
def test_create_office_role_without_projects_succeeds(db, role):
    """Office/owner roles may be created without project_ids — no enforcement applies."""
    owner = _owner(db)
    data = UserCreate(
        full_name="Office Person",
        email=f"office_{role.lower()}@test.com",
        role=UserRole(role),
        project_ids=[],
    )
    user, _pwd = user_service.create_user(db, data, owner["id"])
    assert user.id is not None


# ── update_user enforcement ────────────────────────────────────────────────────

@pytest.mark.parametrize("role", SITE_ROLES)
def test_update_role_to_site_role_without_projects_raises(db, role):
    """Changing an existing user's role to a site role without any project access must raise."""
    owner = _owner(db)
    # Create an office user first
    existing = make_user(db, role="OFFICE_USER")
    existing_id = existing["id"]

    data = UserUpdate(role=UserRole(role))
    with pytest.raises(ValidationError, match="has no project assignments"):
        user_service.update_user(db, existing_id, data, actor_id=owner["id"])


@pytest.mark.parametrize("role", SITE_ROLES)
def test_update_role_to_site_role_with_projects_succeeds(db, role):
    """Changing role to site role succeeds when user already has project access."""
    owner = _owner(db)
    project = make_project(db, owner["id"])
    existing = make_user(db, role="OFFICE_USER")
    import uuid
    db.add(UserProjectAccess(
        user_id=uuid.UUID(existing["id"]),
        project_id=uuid.UUID(project["id"]),
        can_view=True, can_edit=False, can_approve=False,
    ))
    db.flush()

    data = UserUpdate(role=UserRole(role))
    user = user_service.update_user(db, existing["id"], data, actor_id=owner["id"])
    assert user.role == UserRole(role)


# ── project_access_count property ─────────────────────────────────────────────

def test_project_access_count_reflects_assignments(db):
    """User.project_access_count returns the number of assigned projects."""
    owner = _owner(db)
    project1 = make_project(db, owner["id"])
    project2 = make_project(db, owner["id"])

    data = UserCreate(
        full_name="Multi Project Manager",
        email="multi_pm@test.com",
        role=UserRole.SITE_MANAGER,
        project_ids=[project1["id"], project2["id"]],
    )
    user, _ = user_service.create_user(db, data, owner["id"])
    db.refresh(user)
    # Access the property — requires project_access to be loaded
    from sqlalchemy.orm import joinedload
    user = (
        db.query(User)
        .options(joinedload(User.project_access))
        .filter(User.id == user.id)
        .one()
    )
    assert user.project_access_count == 2


def test_project_access_count_zero_for_office_user(db):
    """Office users with no project assignments return project_access_count == 0."""
    owner = _owner(db)
    data = UserCreate(
        full_name="Office Admin",
        email="office_admin_count@test.com",
        role=UserRole.OFFICE_ADMIN,
        project_ids=[],
    )
    user, _ = user_service.create_user(db, data, owner["id"])
    from sqlalchemy.orm import joinedload
    user = (
        db.query(User)
        .options(joinedload(User.project_access))
        .filter(User.id == user.id)
        .one()
    )
    assert user.project_access_count == 0
