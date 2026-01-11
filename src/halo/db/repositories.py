"""
Database repositories for data access layer.

Provides async CRUD operations for all entity types.
"""

import logging
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select, or_, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from halo.db.orm import (
    Alert,
    AuditLog,
    Case,
    Document,
    Entity,
    EntityRelationship,
    EntityType,
    RelationshipType,
    Transaction,
)

logger = logging.getLogger(__name__)


class EntityRepository:
    """Repository for Entity CRUD operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, entity_id: UUID) -> Optional[Entity]:
        """Get entity by ID."""
        result = await self.session.execute(
            select(Entity).where(Entity.id == entity_id)
        )
        return result.scalar_one_or_none()

    async def get_by_personnummer(self, personnummer: str) -> Optional[Entity]:
        """Get entity by personnummer."""
        normalized = personnummer.replace("-", "").replace(" ", "")
        result = await self.session.execute(
            select(Entity).where(Entity.personnummer == normalized)
        )
        return result.scalar_one_or_none()

    async def get_by_organisationsnummer(self, orgnr: str) -> Optional[Entity]:
        """Get entity by organisationsnummer."""
        normalized = orgnr.replace("-", "").replace(" ", "")
        result = await self.session.execute(
            select(Entity).where(Entity.organisationsnummer == normalized)
        )
        return result.scalar_one_or_none()

    async def get_with_relationships(self, entity_id: UUID) -> Optional[Entity]:
        """Get entity with all relationships loaded."""
        result = await self.session.execute(
            select(Entity)
            .where(Entity.id == entity_id)
            .options(
                selectinload(Entity.relationships_from),
                selectinload(Entity.relationships_to),
            )
        )
        return result.scalar_one_or_none()

    async def search(
        self,
        query: str,
        entity_type: Optional[EntityType] = None,
        limit: int = 10,
        offset: int = 0,
    ) -> list[Entity]:
        """
        Search entities by name.

        Uses PostgreSQL ILIKE for case-insensitive matching.
        For production, consider using Elasticsearch.
        """
        stmt = select(Entity).where(
            Entity.display_name.ilike(f"%{query}%")
        )

        if entity_type:
            stmt = stmt.where(Entity.entity_type == entity_type)

        stmt = stmt.offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(
        self,
        entity_type: EntityType,
        display_name: str,
        personnummer: Optional[str] = None,
        organisationsnummer: Optional[str] = None,
        attributes: Optional[dict] = None,
        sources: Optional[list[str]] = None,
    ) -> Entity:
        """Create a new entity."""
        entity = Entity(
            entity_type=entity_type,
            display_name=display_name,
            personnummer=personnummer,
            organisationsnummer=organisationsnummer,
            attributes=attributes or {},
            sources=sources or [],
        )
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def update(
        self,
        entity_id: UUID,
        display_name: Optional[str] = None,
        attributes: Optional[dict] = None,
        sources: Optional[list[str]] = None,
    ) -> Optional[Entity]:
        """Update an existing entity."""
        entity = await self.get_by_id(entity_id)
        if not entity:
            return None

        if display_name:
            entity.display_name = display_name
        if attributes:
            entity.attributes = {**entity.attributes, **attributes}
        if sources:
            entity.sources = list(set(entity.sources + sources))

        entity.updated_at = datetime.utcnow()
        await self.session.flush()
        return entity

    async def list_all(
        self,
        entity_type: Optional[EntityType] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Entity]:
        """List all entities with optional filtering."""
        stmt = select(Entity)

        if entity_type:
            stmt = stmt.where(Entity.entity_type == entity_type)

        stmt = stmt.offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_ids(self, entity_ids: list[UUID]) -> list[Entity]:
        """Get multiple entities by IDs."""
        if not entity_ids:
            return []
        result = await self.session.execute(
            select(Entity).where(Entity.id.in_(entity_ids))
        )
        return list(result.scalars().all())


class RelationshipRepository:
    """Repository for EntityRelationship CRUD operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, rel_id: UUID) -> Optional[EntityRelationship]:
        """Get relationship by ID."""
        result = await self.session.execute(
            select(EntityRelationship).where(EntityRelationship.id == rel_id)
        )
        return result.scalar_one_or_none()

    async def get_for_entity(
        self,
        entity_id: UUID,
        relationship_type: Optional[RelationshipType] = None,
    ) -> list[EntityRelationship]:
        """Get all relationships for an entity (both directions)."""
        stmt = select(EntityRelationship).where(
            or_(
                EntityRelationship.from_entity_id == entity_id,
                EntityRelationship.to_entity_id == entity_id,
            )
        )

        if relationship_type:
            stmt = stmt.where(EntityRelationship.relationship_type == relationship_type)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(
        self,
        from_entity_id: UUID,
        to_entity_id: UUID,
        relationship_type: RelationshipType,
        source: str,
        attributes: Optional[dict] = None,
        confidence: float = 1.0,
        valid_from: Optional[datetime] = None,
        valid_to: Optional[datetime] = None,
    ) -> EntityRelationship:
        """Create a new relationship."""
        rel = EntityRelationship(
            from_entity_id=from_entity_id,
            to_entity_id=to_entity_id,
            relationship_type=relationship_type,
            source=source,
            attributes=attributes or {},
            confidence=confidence,
            valid_from=valid_from,
            valid_to=valid_to,
        )
        self.session.add(rel)
        await self.session.flush()
        return rel

    async def find_path(
        self,
        from_entity_id: UUID,
        to_entity_id: UUID,
        max_depth: int = 4,
    ) -> list[list[UUID]]:
        """
        Find paths between two entities using recursive CTE.

        Returns list of paths, each path is a list of entity IDs.
        """
        # This is a simplified version - for production use a graph database
        # or implement proper BFS/DFS with SQLAlchemy
        paths = []

        # Direct connection check
        direct = await self.session.execute(
            select(EntityRelationship).where(
                or_(
                    (EntityRelationship.from_entity_id == from_entity_id)
                    & (EntityRelationship.to_entity_id == to_entity_id),
                    (EntityRelationship.from_entity_id == to_entity_id)
                    & (EntityRelationship.to_entity_id == from_entity_id),
                )
            )
        )
        if direct.scalar_one_or_none():
            paths.append([from_entity_id, to_entity_id])

        return paths


class AlertRepository:
    """Repository for Alert CRUD operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, alert_id: UUID) -> Optional[Alert]:
        """Get alert by ID."""
        result = await self.session.execute(
            select(Alert).where(Alert.id == alert_id)
        )
        return result.scalar_one_or_none()

    async def get_pending_review(
        self,
        tier: Optional[int] = None,
        limit: int = 50,
    ) -> list[Alert]:
        """Get alerts pending human review."""
        stmt = select(Alert).where(Alert.status == "open")

        if tier == 2:
            stmt = stmt.where(
                Alert.tier == 2,
                Alert.acknowledged_by.is_(None),
            )
        elif tier == 3:
            stmt = stmt.where(
                Alert.tier == 3,
                Alert.approval_decision.is_(None),
            )
        else:
            # All pending
            stmt = stmt.where(
                or_(
                    (Alert.tier == 2) & Alert.acknowledged_by.is_(None),
                    (Alert.tier == 3) & Alert.approval_decision.is_(None),
                )
            )

        stmt = stmt.order_by(Alert.created_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(
        self,
        alert_type: str,
        severity: str,
        title: str,
        description: str,
        confidence: float,
        entity_ids: Optional[list[UUID]] = None,
        transaction_ids: Optional[list[UUID]] = None,
        tier: int = 2,
        affects_person: bool = True,
    ) -> Alert:
        """Create a new alert."""
        alert = Alert(
            alert_type=alert_type,
            severity=severity,
            title=title,
            description=description,
            confidence=confidence,
            entity_ids=entity_ids or [],
            transaction_ids=transaction_ids or [],
            tier=tier,
            affects_person=affects_person,
        )
        self.session.add(alert)
        await self.session.flush()
        return alert

    async def acknowledge(
        self,
        alert_id: UUID,
        user_id: str,
        displayed_at: datetime,
    ) -> Optional[Alert]:
        """Acknowledge a Tier 2 alert."""
        alert = await self.get_by_id(alert_id)
        if not alert or alert.tier != 2:
            return None

        now = datetime.utcnow()
        alert.acknowledged_by = user_id
        alert.acknowledged_at = now
        alert.review_displayed_at = displayed_at
        alert.review_duration_seconds = (now - displayed_at).total_seconds()

        await self.session.flush()
        return alert

    async def approve(
        self,
        alert_id: UUID,
        user_id: str,
        decision: str,
        justification: str,
        displayed_at: datetime,
    ) -> Optional[Alert]:
        """Approve/reject a Tier 3 alert."""
        alert = await self.get_by_id(alert_id)
        if not alert or alert.tier != 3:
            return None

        now = datetime.utcnow()
        alert.approved_by = user_id
        alert.approved_at = now
        alert.approval_decision = decision
        alert.approval_justification = justification
        alert.review_displayed_at = displayed_at
        alert.review_duration_seconds = (now - displayed_at).total_seconds()

        if decision == "approved":
            alert.status = "approved"
        elif decision == "rejected":
            alert.status = "rejected"

        await self.session.flush()
        return alert


class AuditLogRepository:
    """Repository for AuditLog operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def log(
        self,
        user_id: str,
        user_name: str,
        action: str,
        resource_type: str,
        resource_id: Optional[UUID] = None,
        details: Optional[dict] = None,
        case_id: Optional[UUID] = None,
        justification: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> AuditLog:
        """Create an audit log entry."""
        log = AuditLog(
            user_id=user_id,
            user_name=user_name,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details or {},
            case_id=case_id,
            justification=justification,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.session.add(log)
        await self.session.flush()
        return log

    async def get_for_resource(
        self,
        resource_type: str,
        resource_id: UUID,
        limit: int = 100,
    ) -> list[AuditLog]:
        """Get audit logs for a specific resource."""
        result = await self.session.execute(
            select(AuditLog)
            .where(
                AuditLog.resource_type == resource_type,
                AuditLog.resource_id == resource_id,
            )
            .order_by(AuditLog.timestamp.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_for_user(
        self,
        user_id: str,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> list[AuditLog]:
        """Get audit logs for a specific user."""
        stmt = select(AuditLog).where(AuditLog.user_id == user_id)

        if since:
            stmt = stmt.where(AuditLog.timestamp >= since)

        stmt = stmt.order_by(AuditLog.timestamp.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class CaseRepository:
    """Repository for Case CRUD operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, case_id: UUID) -> Optional[Case]:
        """Get case by ID."""
        result = await self.session.execute(
            select(Case).where(Case.id == case_id)
        )
        return result.scalar_one_or_none()

    async def get_by_number(self, case_number: str) -> Optional[Case]:
        """Get case by case number."""
        result = await self.session.execute(
            select(Case).where(Case.case_number == case_number)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        case_number: str,
        title: str,
        description: str,
        assigned_to: Optional[str] = None,
        entity_ids: Optional[list[UUID]] = None,
        alert_ids: Optional[list[UUID]] = None,
    ) -> Case:
        """Create a new case."""
        case = Case(
            case_number=case_number,
            title=title,
            description=description,
            assigned_to=assigned_to,
            entity_ids=entity_ids or [],
            alert_ids=alert_ids or [],
        )
        self.session.add(case)
        await self.session.flush()
        return case

    async def update_status(
        self,
        case_id: UUID,
        status: str,
    ) -> Optional[Case]:
        """Update case status."""
        case = await self.get_by_id(case_id)
        if not case:
            return None

        case.status = status
        case.updated_at = datetime.utcnow()

        if status == "closed":
            case.closed_at = datetime.utcnow()

        await self.session.flush()
        return case

    async def list_open(self, limit: int = 50) -> list[Case]:
        """List open cases."""
        result = await self.session.execute(
            select(Case)
            .where(Case.status == "open")
            .order_by(Case.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())


class UserRepository:
    """Repository for User CRUD operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, user_id: UUID) -> Optional[Any]:
        """Get user by ID."""
        from halo.db.orm import User
        result = await self.session.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: UUID) -> Optional[Any]:
        """Get user by ID (alias for get)."""
        return await self.get(user_id)

    async def get_by_username(self, username: str) -> Optional[Any]:
        """Get user by username."""
        from halo.db.orm import User
        result = await self.session.execute(
            select(User).where(User.username == username)
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Optional[Any]:
        """Get user by email."""
        from halo.db.orm import User
        result = await self.session.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        username: str,
        email: str,
        password: str,
        full_name: str,
        role: str = "viewer",
    ) -> Any:
        """Create a new user."""
        from halo.db.orm import User, UserRole
        from halo.security.auth import hash_password

        user = User(
            username=username,
            email=email,
            password_hash=hash_password(password),
            full_name=full_name,
            role=UserRole(role),
        )
        self.session.add(user)
        await self.session.flush()
        return user

    async def list_users(
        self,
        role: Optional[str] = None,
        is_active: Optional[bool] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Any]:
        """List users with filtering."""
        from halo.db.orm import User, UserRole
        from sqlalchemy import and_

        conditions = []
        if role:
            conditions.append(User.role == UserRole(role))
        if is_active is not None:
            conditions.append(User.is_active == is_active)

        query = select(User)
        if conditions:
            query = query.where(and_(*conditions))

        query = query.order_by(User.created_at.desc()).limit(limit).offset(offset)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count_users(
        self,
        role: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> int:
        """Count users with filtering."""
        from halo.db.orm import User, UserRole
        from sqlalchemy import func, and_

        conditions = []
        if role:
            conditions.append(User.role == UserRole(role))
        if is_active is not None:
            conditions.append(User.is_active == is_active)

        query = select(func.count(User.id))
        if conditions:
            query = query.where(and_(*conditions))

        result = await self.session.execute(query)
        return result.scalar_one()

    async def update(
        self,
        user_id: UUID,
        email: Optional[str] = None,
        full_name: Optional[str] = None,
        role: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> Any:
        """Update user fields."""
        from halo.db.orm import User, UserRole

        result = await self.session.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        if not user:
            return None

        if email is not None:
            user.email = email
        if full_name is not None:
            user.full_name = full_name
        if role is not None:
            user.role = UserRole(role)
        if is_active is not None:
            user.is_active = is_active

        await self.session.flush()
        return user

    async def update_last_login(self, user_id: UUID, ip_address: str) -> None:
        """Update user's last login timestamp and IP."""
        from halo.db.orm import User
        result = await self.session.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        if user:
            user.last_login = datetime.utcnow()
            user.last_login_ip = ip_address
            user.failed_login_attempts = 0
            await self.session.flush()

    async def increment_failed_attempts(self, user_id: UUID) -> None:
        """Increment failed login attempts."""
        from halo.db.orm import User
        result = await self.session.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        if user:
            user.failed_login_attempts += 1
            user.last_failed_login = datetime.utcnow()
            await self.session.flush()

    async def lock_account(self, user_id: UUID, until: datetime) -> None:
        """Lock user account until specified time."""
        from halo.db.orm import User
        result = await self.session.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        if user:
            user.locked_until = until
            await self.session.flush()
