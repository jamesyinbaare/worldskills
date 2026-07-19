"""Script to generate initial dummy data for manual testing and ensure super admin user exists."""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.security import get_password_hash
from app.models import User, UserRole


logger = logging.getLogger(__name__)


async def ensure_super_admin_user(session: AsyncSession) -> None:
    """
    Ensure that a SUPER_ADMIN user exists with the configured email.

    If the user doesn't exist, creates one with the configured email, password, and full name.
    If the user already exists, logs this and continues (idempotent operation).
    """
    try:
        # Check if user with configured email already exists
        stmt = select(User).where(User.email == settings.super_admin_email)
        result = await session.execute(stmt)
        existing_user = result.scalar_one_or_none()

        if existing_user:
            logger.info(f"SUPER_ADMIN user with email {settings.super_admin_email} already exists")
        elif not settings.super_admin_email or not settings.super_admin_password or not settings.super_admin_full_name:
            # Validate that required settings are configured
            logger.warning(
                "SUPER_ADMIN initialization skipped: Required environment variables "
                "(SUPER_ADMIN_EMAIL, SUPER_ADMIN_PASSWORD, SUPER_ADMIN_FULL_NAME) are not set"
            )
        else:
            # Create new SUPER_ADMIN user
            hashed_password = get_password_hash(settings.super_admin_password)
            new_user = User(
                email=settings.super_admin_email,
                hashed_password=hashed_password,
                full_name=settings.super_admin_full_name,
                role=UserRole.SUPER_ADMIN,
                is_active=True,
            )

            session.add(new_user)
            await session.commit()
            logger.info(f"Created SUPER_ADMIN user with email {settings.super_admin_email}")
    except Exception as e:
        logger.error(f"Error ensuring SUPER_ADMIN user exists: {e}", exc_info=True)
        # Don't raise - allow app to start even if user creation fails
        await session.rollback()
