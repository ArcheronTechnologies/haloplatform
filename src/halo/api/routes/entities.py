"""
Entity management API routes.

Provides CRUD operations for entities (people, companies, properties, vehicles).
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from halo.api.deps import AuditRepo, EntityRepo, RelationshipRepo, User
from halo.db.orm import EntityType, RelationshipType

router = APIRouter()


# Request/Response models
class EntityCreate(BaseModel):
    """Request model for creating an entity."""

    entity_type: str = Field(..., description="Type: person, company, property, vehicle")
    display_name: str = Field(..., min_length=1, max_length=255)
    personnummer: Optional[str] = None
    organisationsnummer: Optional[str] = None
    attributes: dict = Field(default_factory=dict)


class EntityUpdate(BaseModel):
    """Request model for updating an entity."""

    display_name: Optional[str] = Field(None, min_length=1, max_length=255)
    attributes: Optional[dict] = None


class EntityResponse(BaseModel):
    """Response model for entity."""

    id: UUID
    entity_type: str
    display_name: str
    personnummer: Optional[str] = None
    organisationsnummer: Optional[str] = None
    attributes: dict
    sources: list[str]

    class Config:
        from_attributes = True


class RelationshipCreate(BaseModel):
    """Request model for creating a relationship."""

    from_entity_id: UUID
    to_entity_id: UUID
    relationship_type: str
    source: str
    attributes: dict = Field(default_factory=dict)
    confidence: float = Field(default=1.0, ge=0, le=1)


class RelationshipResponse(BaseModel):
    """Response model for relationship."""

    id: UUID
    from_entity_id: UUID
    to_entity_id: UUID
    relationship_type: str
    source: str
    attributes: dict
    confidence: float

    class Config:
        from_attributes = True


class PaginatedEntitiesResponse(BaseModel):
    """Paginated entities response."""

    items: list[EntityResponse]
    total: int
    page: int
    limit: int


@router.get("", response_model=PaginatedEntitiesResponse)
async def list_entities(
    entity_repo: EntityRepo,
    audit_repo: AuditRepo,
    user: User,
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=200, description="Items per page"),
    type: Optional[str] = Query(None, description="Filter by entity type"),
    risk_level: Optional[str] = Query(None, description="Filter by risk level"),
):
    """List entities with pagination and filters."""
    e_type = None
    if type:
        try:
            e_type = EntityType(type)
        except ValueError:
            pass

    # Get entities (simplified for now)
    entities = await entity_repo.search(
        query="",
        entity_type=e_type,
        limit=limit * 5,
        offset=0,
    )

    # Filter by risk_level if provided
    if risk_level:
        entities = [e for e in entities if getattr(e, 'risk_level', None) == risk_level]

    total = len(entities)

    # Paginate
    start = (page - 1) * limit
    end = start + limit
    page_entities = entities[start:end]

    # Convert to response models
    items = [
        EntityResponse(
            id=e.id,
            entity_type=e.entity_type.value,
            display_name=e.display_name,
            personnummer=e.personnummer,
            organisationsnummer=e.organisationsnummer,
            attributes=e.attributes,
            sources=e.sources,
        )
        for e in page_entities
    ]

    await audit_repo.log(
        user_id=user.user_id,
        user_name=user.user_name,
        action="view",
        resource_type="entity_list",
        details={"type": type, "risk_level": risk_level, "count": len(items)},
    )

    return PaginatedEntitiesResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
    )


@router.get("/{entity_id}", response_model=EntityResponse)
async def get_entity(
    entity_id: UUID,
    entity_repo: EntityRepo,
    audit_repo: AuditRepo,
    user: User,
):
    """
    Get entity by ID.

    All access is logged for audit compliance.
    """
    entity = await entity_repo.get_by_id(entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    # Log access
    await audit_repo.log(
        user_id=user.user_id,
        user_name=user.user_name,
        action="view",
        resource_type="entity",
        resource_id=entity_id,
    )

    return entity


@router.get("/{entity_id}/relationships", response_model=list[RelationshipResponse])
async def get_entity_relationships(
    entity_id: UUID,
    relationship_repo: RelationshipRepo,
    entity_repo: EntityRepo,
    audit_repo: AuditRepo,
    user: User,
    relationship_type: Optional[str] = None,
):
    """Get all relationships for an entity."""
    # Verify entity exists
    entity = await entity_repo.get_by_id(entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    rel_type = None
    if relationship_type:
        try:
            rel_type = RelationshipType(relationship_type)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid relationship type: {relationship_type}",
            )

    relationships = await relationship_repo.get_for_entity(entity_id, rel_type)

    # Log access
    await audit_repo.log(
        user_id=user.user_id,
        user_name=user.user_name,
        action="view",
        resource_type="entity_relationships",
        resource_id=entity_id,
        details={"count": len(relationships)},
    )

    return relationships


@router.post("", response_model=EntityResponse, status_code=201)
async def create_entity(
    data: EntityCreate,
    entity_repo: EntityRepo,
    audit_repo: AuditRepo,
    user: User,
):
    """Create a new entity."""
    try:
        entity_type = EntityType(data.entity_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid entity type: {data.entity_type}",
        )

    entity = await entity_repo.create(
        entity_type=entity_type,
        display_name=data.display_name,
        personnummer=data.personnummer,
        organisationsnummer=data.organisationsnummer,
        attributes=data.attributes,
    )

    # Log creation
    await audit_repo.log(
        user_id=user.user_id,
        user_name=user.user_name,
        action="create",
        resource_type="entity",
        resource_id=entity.id,
        details={"entity_type": data.entity_type},
    )

    return entity


@router.patch("/{entity_id}", response_model=EntityResponse)
async def update_entity(
    entity_id: UUID,
    data: EntityUpdate,
    entity_repo: EntityRepo,
    audit_repo: AuditRepo,
    user: User,
):
    """Update an existing entity."""
    entity = await entity_repo.update(
        entity_id=entity_id,
        display_name=data.display_name,
        attributes=data.attributes,
    )

    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    # Log update
    await audit_repo.log(
        user_id=user.user_id,
        user_name=user.user_name,
        action="update",
        resource_type="entity",
        resource_id=entity_id,
        details={"updated_fields": [k for k, v in data.model_dump().items() if v is not None]},
    )

    return entity


@router.post("/relationships", response_model=RelationshipResponse, status_code=201)
async def create_relationship(
    data: RelationshipCreate,
    relationship_repo: RelationshipRepo,
    entity_repo: EntityRepo,
    audit_repo: AuditRepo,
    user: User,
):
    """Create a relationship between two entities."""
    # Verify both entities exist
    from_entity = await entity_repo.get_by_id(data.from_entity_id)
    if not from_entity:
        raise HTTPException(status_code=404, detail="From entity not found")

    to_entity = await entity_repo.get_by_id(data.to_entity_id)
    if not to_entity:
        raise HTTPException(status_code=404, detail="To entity not found")

    try:
        rel_type = RelationshipType(data.relationship_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid relationship type: {data.relationship_type}",
        )

    relationship = await relationship_repo.create(
        from_entity_id=data.from_entity_id,
        to_entity_id=data.to_entity_id,
        relationship_type=rel_type,
        source=data.source,
        attributes=data.attributes,
        confidence=data.confidence,
    )

    # Log creation
    await audit_repo.log(
        user_id=user.user_id,
        user_name=user.user_name,
        action="create",
        resource_type="relationship",
        resource_id=relationship.id,
        details={
            "from_entity_id": str(data.from_entity_id),
            "to_entity_id": str(data.to_entity_id),
            "relationship_type": data.relationship_type,
        },
    )

    return relationship


@router.get("/by-personnummer/{personnummer}", response_model=EntityResponse)
async def get_by_personnummer(
    personnummer: str,
    entity_repo: EntityRepo,
    audit_repo: AuditRepo,
    user: User,
):
    """Get entity by Swedish personnummer."""
    entity = await entity_repo.get_by_personnummer(personnummer)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    # Log access
    await audit_repo.log(
        user_id=user.user_id,
        user_name=user.user_name,
        action="search",
        resource_type="entity",
        resource_id=entity.id,
        details={"search_type": "personnummer"},
    )

    return entity


@router.get("/by-orgnr/{orgnr}", response_model=EntityResponse)
async def get_by_organisationsnummer(
    orgnr: str,
    entity_repo: EntityRepo,
    audit_repo: AuditRepo,
    user: User,
):
    """Get entity by Swedish organisationsnummer."""
    entity = await entity_repo.get_by_organisationsnummer(orgnr)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    # Log access
    await audit_repo.log(
        user_id=user.user_id,
        user_name=user.user_name,
        action="search",
        resource_type="entity",
        resource_id=entity.id,
        details={"search_type": "organisationsnummer"},
    )

    return entity


# Transaction models
class TransactionResponse(BaseModel):
    """Response model for transaction."""

    id: str
    amount: float
    currency: str = "SEK"
    timestamp: str
    transaction_type: str
    from_entity_id: Optional[str] = None
    from_entity_name: Optional[str] = None
    to_entity_id: Optional[str] = None
    to_entity_name: Optional[str] = None
    description: Optional[str] = None
    risk_score: Optional[float] = None


class PaginatedTransactions(BaseModel):
    """Paginated transactions response."""

    items: list[TransactionResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# Timeline models
class TimelineEvent(BaseModel):
    """Timeline event model."""

    id: str
    event_type: str
    timestamp: str
    title: str
    description: Optional[str] = None
    related_entity_ids: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


@router.get("/{entity_id}/transactions", response_model=PaginatedTransactions)
async def get_entity_transactions(
    entity_id: UUID,
    entity_repo: EntityRepo,
    audit_repo: AuditRepo,
    user: User,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    """
    Get transactions involving an entity.

    Returns paginated list of financial transactions.
    """
    # Verify entity exists
    entity = await entity_repo.get_by_id(entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    # Log access
    await audit_repo.log(
        user_id=user.user_id,
        user_name=user.user_name,
        action="view",
        resource_type="entity_transactions",
        resource_id=entity_id,
    )

    # In production, fetch from transaction store/database
    # For now return empty paginated result
    return PaginatedTransactions(
        items=[],
        total=0,
        page=page,
        page_size=limit,
        total_pages=0,
    )


@router.get("/{entity_id}/timeline", response_model=list[TimelineEvent])
async def get_entity_timeline(
    entity_id: UUID,
    entity_repo: EntityRepo,
    audit_repo: AuditRepo,
    user: User,
    limit: int = Query(50, ge=1, le=200),
):
    """
    Get timeline of events for an entity.

    Returns chronological list of significant events:
    - Entity creation/updates
    - Relationship changes
    - Risk score changes
    - Alerts generated
    - Investigation events
    """
    # Verify entity exists
    entity = await entity_repo.get_by_id(entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    # Log access
    await audit_repo.log(
        user_id=user.user_id,
        user_name=user.user_name,
        action="view",
        resource_type="entity_timeline",
        resource_id=entity_id,
    )

    # In production, aggregate events from multiple sources
    # For now return empty list
    return []
