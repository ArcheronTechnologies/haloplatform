"""
Case-level access control for Halo platform.

Implements need-to-know principle required by Säkerhetsskyddslagen.
RBAC alone is insufficient - analysts shouldn't access every case.

Per security framework section 3.1.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from halo.db.orm import Case, CaseAccessLevel, CaseAssignment, User, UserRole
from halo.security.auth import User as AuthUser

logger = logging.getLogger(__name__)


class CaseAccessManager:
    """
    Case-level access control (need-to-know enforcement).

    Users must be explicitly assigned to cases to access them.
    Admins can bypass for emergency access.
    """

    def __init__(self, db: AsyncSession):
        """
        Initialize access manager.

        Args:
            db: Database session
        """
        self._db = db

    async def check_access(
        self, user: AuthUser, case_id: UUID, required_level: str = "read"
    ) -> bool:
        """
        Check if user has required access level to a case.

        Args:
            user: The authenticated user
            case_id: The case to check access for
            required_level: "read", "write", or "owner"

        Returns:
            True if access is granted, False otherwise
        """
        # Admins bypass case-level access
        if user.role in (UserRole.ADMIN, UserRole.SYSTEM):
            return True

        # Check for active assignment
        assignment = await self._get_active_assignment(user.id, case_id)

        if not assignment:
            return False

        return self._level_sufficient(assignment.access_level, required_level)

    async def require_access(
        self, user: AuthUser, case_id: UUID, required_level: str = "read"
    ) -> CaseAssignment:
        """
        Require access to a case, raising HTTPException if denied.

        Args:
            user: The authenticated user
            case_id: The case to access
            required_level: "read", "write", or "owner"

        Returns:
            The CaseAssignment if access granted

        Raises:
            HTTPException: 403 if access denied, 404 if case not found
        """
        # Check case exists
        case = await self._db.get(Case, case_id)
        if not case:
            raise HTTPException(status_code=404, detail="Ärende ej funnet")

        # Admins bypass
        if user.role in (UserRole.ADMIN, UserRole.SYSTEM):
            logger.info(f"Admin {user.id} accessed case {case_id}")
            return None  # No assignment needed for admin

        # Check assignment
        assignment = await self._get_active_assignment(user.id, case_id)

        if not assignment:
            logger.warning(
                f"User {user.id} denied access to case {case_id}: no assignment"
            )
            raise HTTPException(
                status_code=403,
                detail="Du har inte behörighet till detta ärende",
            )

        if not self._level_sufficient(assignment.access_level, required_level):
            logger.warning(
                f"User {user.id} denied {required_level} access to case {case_id}: "
                f"has {assignment.access_level.value}"
            )
            raise HTTPException(
                status_code=403,
                detail=f"Din behörighet ({assignment.access_level.value}) "
                f"är inte tillräcklig för denna åtgärd",
            )

        return assignment

    async def grant_access(
        self,
        granter: AuthUser,
        case_id: UUID,
        user_id: UUID,
        level: str,
        justification: str,
        expires_in_days: Optional[int] = None,
    ) -> CaseAssignment:
        """
        Grant case access to a user.

        Requires owner access or admin role.

        Args:
            granter: User granting access
            case_id: Case to grant access to
            user_id: User to grant access to
            level: Access level ("read", "write", "owner")
            justification: Reason for granting access (required for audit)
            expires_in_days: Optional expiration (for temporary access)

        Returns:
            The created CaseAssignment

        Raises:
            HTTPException: 403 if granter lacks permission
        """
        # Check granter has owner access or is admin
        if granter.role not in (UserRole.ADMIN, UserRole.SYSTEM):
            granter_assignment = await self._get_active_assignment(granter.id, case_id)
            if not granter_assignment or granter_assignment.access_level != CaseAccessLevel.OWNER:
                raise HTTPException(
                    status_code=403,
                    detail="Endast ärendeägare kan tilldela behörigheter",
                )

        # Validate justification
        if not justification or len(justification.strip()) < 10:
            raise HTTPException(
                status_code=400,
                detail="Motivering krävs (minst 10 tecken)",
            )

        # Convert level string to enum
        try:
            access_level = CaseAccessLevel(level)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Ogiltig behörighetsnivå: {level}",
            )

        # Check if user already has access
        existing = await self._get_active_assignment(user_id, case_id)
        if existing:
            # Revoke old assignment
            existing.revoked_at = datetime.utcnow()
            existing.revoked_by = granter.id

        # Create new assignment
        assignment = CaseAssignment(
            case_id=case_id,
            user_id=user_id,
            access_level=access_level,
            granted_by=granter.id,
            justification=justification,
            expires_at=(
                datetime.utcnow() + timedelta(days=expires_in_days)
                if expires_in_days
                else None
            ),
        )

        self._db.add(assignment)
        await self._db.flush()

        logger.info(
            f"User {granter.id} granted {level} access to case {case_id} "
            f"for user {user_id}"
        )

        return assignment

    async def revoke_access(
        self,
        revoker: AuthUser,
        case_id: UUID,
        user_id: UUID,
    ) -> bool:
        """
        Revoke a user's access to a case.

        Args:
            revoker: User revoking access
            case_id: Case to revoke access from
            user_id: User whose access to revoke

        Returns:
            True if access was revoked, False if no access existed

        Raises:
            HTTPException: 403 if revoker lacks permission
        """
        # Check revoker has owner access or is admin
        if revoker.role not in (UserRole.ADMIN, UserRole.SYSTEM):
            revoker_assignment = await self._get_active_assignment(revoker.id, case_id)
            if not revoker_assignment or revoker_assignment.access_level != CaseAccessLevel.OWNER:
                raise HTTPException(
                    status_code=403,
                    detail="Endast ärendeägare kan ta bort behörigheter",
                )

        assignment = await self._get_active_assignment(user_id, case_id)
        if not assignment:
            return False

        assignment.revoked_at = datetime.utcnow()
        assignment.revoked_by = revoker.id

        logger.info(
            f"User {revoker.id} revoked access to case {case_id} for user {user_id}"
        )

        return True

    async def get_case_assignments(self, case_id: UUID) -> list[CaseAssignment]:
        """
        Get all active assignments for a case.

        Args:
            case_id: The case ID

        Returns:
            List of active CaseAssignment objects
        """
        result = await self._db.execute(
            select(CaseAssignment).where(
                and_(
                    CaseAssignment.case_id == case_id,
                    CaseAssignment.revoked_at.is_(None),
                )
            )
        )
        assignments = result.scalars().all()

        # Filter expired
        now = datetime.utcnow()
        return [
            a for a in assignments
            if a.expires_at is None or a.expires_at > now
        ]

    async def get_user_cases(self, user_id: UUID) -> list[CaseAssignment]:
        """
        Get all cases a user has access to.

        Args:
            user_id: The user ID

        Returns:
            List of active CaseAssignment objects
        """
        result = await self._db.execute(
            select(CaseAssignment).where(
                and_(
                    CaseAssignment.user_id == user_id,
                    CaseAssignment.revoked_at.is_(None),
                )
            )
        )
        assignments = result.scalars().all()

        # Filter expired
        now = datetime.utcnow()
        return [
            a for a in assignments
            if a.expires_at is None or a.expires_at > now
        ]

    async def _get_active_assignment(
        self, user_id: UUID, case_id: UUID
    ) -> Optional[CaseAssignment]:
        """
        Get active assignment for a user and case.

        Args:
            user_id: The user ID
            case_id: The case ID

        Returns:
            CaseAssignment if exists and active, None otherwise
        """
        result = await self._db.execute(
            select(CaseAssignment).where(
                and_(
                    CaseAssignment.case_id == case_id,
                    CaseAssignment.user_id == user_id,
                    CaseAssignment.revoked_at.is_(None),
                )
            )
        )
        assignment = result.scalar_one_or_none()

        if not assignment:
            return None

        # Check expiration
        if assignment.expires_at and assignment.expires_at < datetime.utcnow():
            return None

        return assignment

    @staticmethod
    def _level_sufficient(has_level: CaseAccessLevel, needs_level: str) -> bool:
        """
        Check if a user's access level is sufficient.

        Args:
            has_level: The level the user has
            needs_level: The level required ("read", "write", "owner")

        Returns:
            True if sufficient
        """
        level_hierarchy = {
            "read": [CaseAccessLevel.READ, CaseAccessLevel.WRITE, CaseAccessLevel.OWNER],
            "write": [CaseAccessLevel.WRITE, CaseAccessLevel.OWNER],
            "owner": [CaseAccessLevel.OWNER],
        }

        required_levels = level_hierarchy.get(needs_level, [])
        return has_level in required_levels
