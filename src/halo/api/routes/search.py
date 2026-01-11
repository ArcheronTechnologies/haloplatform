"""
Search API routes.

Provides search functionality across entities.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from halo.api.deps import AuditRepo, EntityRepo, User
from halo.db.orm import EntityType

router = APIRouter()


class SearchResult(BaseModel):
    """Single search result."""

    id: UUID
    entity_type: str
    display_name: str
    personnummer: Optional[str] = None
    organisationsnummer: Optional[str] = None
    attributes: dict
    score: float = 1.0

    class Config:
        from_attributes = True


class SearchResponse(BaseModel):
    """Search response with results and metadata."""

    query: str
    total: int
    results: list[SearchResult]


@router.get("", response_model=SearchResponse)
async def search_entities(
    entity_repo: EntityRepo,
    audit_repo: AuditRepo,
    user: User,
    q: str = Query(..., min_length=1, description="Search query"),
    entity_type: Optional[str] = Query(None, description="Filter by entity type"),
    limit: int = Query(10, ge=1, le=100, description="Maximum results"),
    offset: int = Query(0, ge=0, description="Result offset"),
):
    """
    Search entities by name.

    Supports filtering by entity type (person, company, property, vehicle).
    All searches are logged for audit compliance.
    """
    # Validate entity type if provided
    e_type = None
    if entity_type:
        try:
            e_type = EntityType(entity_type)
        except ValueError:
            # Invalid type, return empty results
            return SearchResponse(query=q, total=0, results=[])

    entities = await entity_repo.search(
        query=q,
        entity_type=e_type,
        limit=limit,
        offset=offset,
    )

    # Convert to search results
    results = [
        SearchResult(
            id=e.id,
            entity_type=e.entity_type.value,
            display_name=e.display_name,
            personnummer=e.personnummer,
            organisationsnummer=e.organisationsnummer,
            attributes=e.attributes,
            score=1.0,  # Simple search doesn't have relevance scoring
        )
        for e in entities
    ]

    # Log search
    await audit_repo.log(
        user_id=user.user_id,
        user_name=user.user_name,
        action="search",
        resource_type="entity",
        details={
            "query": q,
            "entity_type": entity_type,
            "result_count": len(results),
        },
    )

    return SearchResponse(
        query=q,
        total=len(results),
        results=results,
    )


@router.get("/companies", response_model=SearchResponse)
async def search_companies(
    entity_repo: EntityRepo,
    audit_repo: AuditRepo,
    user: User,
    q: str = Query(..., min_length=1, description="Company name search"),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """Search for companies by name."""
    entities = await entity_repo.search(
        query=q,
        entity_type=EntityType.COMPANY,
        limit=limit,
        offset=offset,
    )

    results = [
        SearchResult(
            id=e.id,
            entity_type=e.entity_type.value,
            display_name=e.display_name,
            organisationsnummer=e.organisationsnummer,
            attributes=e.attributes,
        )
        for e in entities
    ]

    await audit_repo.log(
        user_id=user.user_id,
        user_name=user.user_name,
        action="search",
        resource_type="company",
        details={"query": q, "result_count": len(results)},
    )

    return SearchResponse(query=q, total=len(results), results=results)


@router.get("/persons", response_model=SearchResponse)
async def search_persons(
    entity_repo: EntityRepo,
    audit_repo: AuditRepo,
    user: User,
    q: str = Query(..., min_length=1, description="Person name search"),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """
    Search for persons by name.

    Note: Person searches are logged with extra scrutiny for compliance.
    """
    entities = await entity_repo.search(
        query=q,
        entity_type=EntityType.PERSON,
        limit=limit,
        offset=offset,
    )

    results = [
        SearchResult(
            id=e.id,
            entity_type=e.entity_type.value,
            display_name=e.display_name,
            personnummer=e.personnummer,
            attributes=e.attributes,
        )
        for e in entities
    ]

    # Extra logging for person searches (compliance requirement)
    await audit_repo.log(
        user_id=user.user_id,
        user_name=user.user_name,
        action="search",
        resource_type="person",
        details={
            "query": q,
            "result_count": len(results),
            "result_ids": [str(r.id) for r in results],
        },
    )

    return SearchResponse(query=q, total=len(results), results=results)
