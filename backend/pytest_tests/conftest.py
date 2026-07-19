"""Pytest fixtures for SCMS backend tests.

Requires a reachable Postgres (compose or CI service). Set:
  DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/dbname
  MOCK_DATABASE=true
  USE_NULL_POOL=true
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from datetime import date, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.pool import NullPool

# Force test database when running pytest (override .env docker hostname)
os.environ["MOCK_DATABASE"] = "true"
os.environ["USE_NULL_POOL"] = "true"
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("AUDIT_HMAC_SECRET", "test-audit-secret")
os.environ.setdefault("STORAGE_ROOT", "/tmp/scms-test-storage")

# Prefer host-reachable Postgres (compose publishes 5432); override docker DNS name from .env
_test_db = os.environ.get("TEST_DATABASE_URL")
if _test_db:
    os.environ["DATABASE_URL"] = _test_db
else:
    # Replace docker service hostname with localhost for host-side pytest
    existing = os.environ.get("DATABASE_URL", "")
    if "world-skills-postgres" in existing:
        os.environ["DATABASE_URL"] = existing.replace("world-skills-postgres", "127.0.0.1")
    elif not existing:
        os.environ["DATABASE_URL"] = (
            "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/world_skills_test"
        )
    # Ensure test DB name so we don't wipe the main database
    url = os.environ["DATABASE_URL"]
    if url.rsplit("/", 1)[-1] in {"world_skills_db", ""}:
        os.environ["DATABASE_URL"] = url.rsplit("/", 1)[0] + "/world_skills_test"


from app.core.security import get_password_hash  # noqa: E402
from app.dependencies.database import (  # noqa: E402
    TestingDatabaseSessionManager,
    convert_to_async_url,
    db_settings,
    get_db_session,
)
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    AgeRule,
    Cycle,
    MarkingScheme,
    Pathway,
    Skill,
    Stage,
    User,
    UserRole,
)


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest_asyncio.fixture(scope="session")
async def session_manager() -> AsyncIterator[TestingDatabaseSessionManager]:
    url = convert_to_async_url(db_settings.database_url or os.environ["DATABASE_URL"])
    manager = TestingDatabaseSessionManager(url, {"echo": False, "poolclass": NullPool})
    await manager.configure()
    yield manager
    await manager.close()


@pytest_asyncio.fixture
async def db_session(session_manager: TestingDatabaseSessionManager) -> AsyncIterator[AsyncSession]:
    async with session_manager.session() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(session_manager: TestingDatabaseSessionManager) -> AsyncIterator[AsyncClient]:
    async def _override() -> AsyncIterator[AsyncSession]:
        async with session_manager.session() as session:
            yield session

    app.dependency_overrides[get_db_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def admin_user(session_manager: TestingDatabaseSessionManager) -> User:
    async with session_manager.session() as session:
        email = f"admin-{uuid.uuid4().hex[:8]}@example.com"
        user = User(
            email=email,
            full_name="Test Admin",
            hashed_password=get_password_hash("admin-pass-123"),
            role=UserRole.ADMIN,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        user_id = user.id

    async with session_manager.session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        return result.scalar_one()


@pytest_asyncio.fixture
async def competitor_user(session_manager: TestingDatabaseSessionManager) -> User:
    async with session_manager.session() as session:
        user = User(
            email=f"comp-{uuid.uuid4().hex[:8]}@example.com",
            full_name="Test Competitor",
            hashed_password=get_password_hash("comp-pass-123"),
            role=UserRole.COMPETITOR,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        user_id = user.id

    async with session_manager.session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        return result.scalar_one()


@pytest_asyncio.fixture
async def admin_token(client: AsyncClient, admin_user: User) -> str:
    resp = await client.post(
        "/auth/login",
        json={"email": admin_user.email, "password": "admin-pass-123"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest_asyncio.fixture
async def auth_headers(admin_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {admin_token}"}


def cycle_payload(**overrides: object) -> dict:
    today = date.today()
    base: dict = {
        "name": f"WS Ghana {uuid.uuid4().hex[:6]}",
        "period": {
            "start": today.isoformat(),
            "end": (today + timedelta(days=120)).isoformat(),
        },
        "timeZone": "Africa/Accra",
        "organisingBody": {"name": "CTVET"},
        "branding": {"primaryColor": "#009739"},
        "languages": ["en"],
    }
    base.update(overrides)
    return base


async def seed_complete_config(session: AsyncSession, cycle: Cycle) -> None:
    """Minimal complete skill/stage graph so activation can succeed."""
    age = AgeRule(cycle_id=cycle.id, name="U25", max_age=25)
    path = Pathway(cycle_id=cycle.id, name="National")
    scheme = MarkingScheme(cycle_id=cycle.id, name="CIS")
    session.add_all([age, path, scheme])
    await session.flush()
    skill = Skill(
        cycle_id=cycle.id,
        name="Web Development",
        age_rule_id=age.id,
        pathway_id=path.id,
        scheme_id=scheme.id,
        capacity=20,
        active=True,
    )
    session.add(skill)
    await session.flush()
    session.add(
        Stage(
            cycle_id=cycle.id,
            skill_id=skill.id,
            name="Regional",
            order=1,
            quota=20,
            scheme_id=scheme.id,
        )
    )
    session.add(
        Stage(
            cycle_id=cycle.id,
            skill_id=skill.id,
            name="National",
            order=2,
            quota=10,
            scheme_id=scheme.id,
        )
    )
    await session.commit()
