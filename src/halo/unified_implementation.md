# Halo Implementation Plan for Claude Code

## Instructions for Claude Code

This document contains step-by-step implementation instructions. Execute each phase in order. Each task has explicit acceptance criteria—do not proceed to the next task until criteria are met.

**Project Location**: Create all files in `~/projects/halo/` (actual: `/Users/timothyaikenhead/Desktop/new-folder/`)
**Python Version**: 3.12
**Package Manager**: uv (preferred) or pip

---

## Implementation Progress

**Last Updated**: 2026-01-08

| Phase                            | Status      | Notes                                                            |
| -------------------------------- | ----------- | ---------------------------------------------------------------- |
| Phase 1: Project Setup           | ✅ Complete | src/halo/ structure, Docker, FastAPI                             |
| Phase 2: Database Models         | ✅ Complete | Ontology ORM models (onto_* tables)                              |
| Phase 3: Swedish Utilities       | ✅ Complete | personnummer, orgnummer, address, company_name                   |
| Phase 4: Entity Resolution       | ✅ Complete | Blocking, comparison, exact-match resolver                       |
| Phase 5: Shell Network Detection | ✅ Complete | DB-backed queries, POST endpoint                                 |
| Phase 6: Remaining Implementation| ✅ Complete | Derivation, audit, lifecycle, referral, evidence, impact, fusion |

### Additional Modules Implemented Beyond Plan

- **EVENT entity type**: Added to EntityType enum with EventAttributes ORM model and migration
- **OntologyBase**: Separated from legacy halo.db.Base to avoid class conflicts
- **Security modules**: BankID client, OIDC provider, CSRF protection
- **Review workflow**: Tiered human-in-loop review system
- **NLP integration**: Document analysis and entity extraction
- **Financial crime detection**: AML patterns and transaction analysis
- **Investigation support**: Case management and collaboration
- **ML pattern detection**: Kept for pattern detection (not resolution per spec)

### Remaining Work

- [ ] CI/CD pipeline setup
- [ ] End-to-end integration tests
- [ ] Performance benchmarking against targets
- [ ] API documentation (OpenAPI/Swagger)
- [ ] Deployment to Scaleway
- [ ] Production monitoring setup

---

## Phase 1: Project Setup (Week 1)

### Task 1.1: Initialize Repository

```bash
mkdir -p ~/projects/halo
cd ~/projects/halo
git init
```

Create `pyproject.toml`:

```toml
[project]
name = "halo"
version = "0.1.0"
description = "Swedish Organized Crime Intelligence Platform"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.109.0",
    "uvicorn[standard]>=0.27.0",
    "sqlalchemy>=2.0.25",
    "asyncpg>=0.29.0",
    "alembic>=1.13.0",
    "pydantic>=2.5.0",
    "pydantic-settings>=2.1.0",
    "httpx>=0.26.0",
    "celery>=5.3.0",
    "redis>=5.0.0",
    "jellyfish>=1.0.0",
    "metaphone>=0.6",
    "geoalchemy2>=0.14.0",
    "shapely>=2.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=4.1.0",
    "ruff>=0.1.0",
    "mypy>=1.8.0",
    "pre-commit>=3.6.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP"]

[tool.mypy]
python_version = "3.12"
strict = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

Create directory structure:

```bash
mkdir -p src/halo/{models,schemas,api,ingestion,resolution,patterns,derivation,swedish,utils}
mkdir -p tests/{test_api,test_ingestion,test_resolution,test_patterns,test_swedish,fixtures}
mkdir -p alembic/versions
mkdir -p docker
mkdir -p scripts
touch src/halo/__init__.py
touch src/halo/{models,schemas,api,ingestion,resolution,patterns,derivation,swedish,utils}/__init__.py
touch tests/__init__.py
touch tests/conftest.py
```

**Acceptance Criteria**:
- [ ] `pyproject.toml` exists and is valid
- [ ] All directories created
- [ ] `uv sync` or `pip install -e ".[dev]"` succeeds

### Task 1.2: Create Configuration

Create `src/halo/config.py`:

```python
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://halo:halo@localhost:5432/halo"
    database_pool_size: int = 20
    
    # Redis
    redis_url: str = "redis://localhost:6379"
    
    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    debug: bool = False
    
    # Resolution thresholds
    person_auto_match_threshold: float = 0.95
    person_human_review_min: float = 0.60
    company_auto_match_threshold: float = 0.95
    company_human_review_min: float = 0.60
    address_auto_match_threshold: float = 0.90
    address_human_review_min: float = 0.50
    
    # External APIs
    bolagsverket_api_key: str = ""
    bolagsverket_base_url: str = "https://data.bolagsverket.se/v3"
    
    # System
    version: str = "0.1.0"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

Create `.env.example`:

```
DATABASE_URL=postgresql+asyncpg://halo:halo@localhost:5432/halo
REDIS_URL=redis://localhost:6379
BOLAGSVERKET_API_KEY=your_api_key_here
DEBUG=true
```

**Acceptance Criteria**:
- [ ] `config.py` imports without error
- [ ] `get_settings()` returns Settings instance
- [ ] `.env.example` contains all required variables

### Task 1.3: Create Database Connection

Create `src/halo/database.py`:

```python
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from halo.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    pool_size=settings.database_pool_size,
    echo=settings.debug,
)

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for database sessions."""
    async with get_db_session() as session:
        yield session
```

**Acceptance Criteria**:
- [ ] `database.py` imports without error
- [ ] `Base` class is defined
- [ ] `get_db_session` is an async context manager

### Task 1.4: Create Docker Configuration

Create `docker/Dockerfile`:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Copy application
COPY src/ src/
COPY alembic/ alembic/
COPY alembic.ini .

# Run
CMD ["uvicorn", "halo.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Create `docker/docker-compose.yml`:

```yaml
version: '3.8'

services:
  db:
    image: postgis/postgis:16-3.4
    environment:
      POSTGRES_DB: halo
      POSTGRES_USER: halo
      POSTGRES_PASSWORD: halo
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./init-extensions.sql:/docker-entrypoint-initdb.d/init.sql
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U halo"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7.2-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

volumes:
  postgres_data:
  redis_data:
```

Create `docker/init-extensions.sql`:

```sql
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "postgis";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
```

**Acceptance Criteria**:
- [ ] `docker compose -f docker/docker-compose.yml up -d` starts services
- [ ] PostgreSQL is accessible on port 5432
- [ ] Redis is accessible on port 6379

### Task 1.5: Create FastAPI Application

Create `src/halo/main.py`:

```python
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from halo.config import get_settings
from halo.api import entities, patterns, resolution, health

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Startup
    yield
    # Shutdown


app = FastAPI(
    title="Halo",
    description="Swedish Organized Crime Intelligence Platform",
    version=settings.version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router)
app.include_router(entities.router)
app.include_router(patterns.router)
app.include_router(resolution.router)
```

Create `src/halo/api/health.py`:

```python
from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict:
    return {"status": "healthy"}


@router.get("/ready")
async def readiness_check() -> dict:
    # TODO: Check database and redis connections
    return {"status": "ready"}
```

Create placeholder routers:

`src/halo/api/entities.py`:
```python
from fastapi import APIRouter

router = APIRouter(prefix="/entities", tags=["entities"])


@router.get("/{entity_id}")
async def get_entity(entity_id: str) -> dict:
    # TODO: Implement
    return {"id": entity_id, "status": "not_implemented"}
```

`src/halo/api/patterns.py`:
```python
from fastapi import APIRouter

router = APIRouter(prefix="/patterns", tags=["patterns"])


@router.post("/shell-network")
async def detect_shell_networks() -> dict:
    # TODO: Implement
    return {"matches": [], "status": "not_implemented"}
```

`src/halo/api/resolution.py`:
```python
from fastapi import APIRouter

router = APIRouter(prefix="/resolution", tags=["resolution"])


@router.get("/queue")
async def get_review_queue() -> dict:
    # TODO: Implement
    return {"items": [], "status": "not_implemented"}
```

**Acceptance Criteria**:
- [ ] `uvicorn halo.main:app --reload` starts server
- [ ] `GET /health` returns `{"status": "healthy"}`
- [ ] `GET /docs` shows Swagger UI

---

## Phase 2: Database Models (Week 2)

### Task 2.1: Create Enum Types

Create `src/halo/models/enums.py`:

```python
import enum


class EntityType(str, enum.Enum):
    PERSON = "PERSON"
    COMPANY = "COMPANY"
    ADDRESS = "ADDRESS"


class EntityStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    MERGED = "MERGED"
    SPLIT = "SPLIT"
    ANONYMIZED = "ANONYMIZED"


class FactType(str, enum.Enum):
    ATTRIBUTE = "ATTRIBUTE"
    RELATIONSHIP = "RELATIONSHIP"


class SourceType(str, enum.Enum):
    BOLAGSVERKET_HVD = "BOLAGSVERKET_HVD"
    BOLAGSVERKET_ANNUAL_REPORT = "BOLAGSVERKET_ANNUAL_REPORT"
    ALLABOLAG_SCRAPE = "ALLABOLAG_SCRAPE"
    MANUAL_ENTRY = "MANUAL_ENTRY"
    DERIVED_COMPUTATION = "DERIVED_COMPUTATION"


class ResolutionStatus(str, enum.Enum):
    PENDING = "PENDING"
    AUTO_MATCHED = "AUTO_MATCHED"
    HUMAN_MATCHED = "HUMAN_MATCHED"
    AUTO_REJECTED = "AUTO_REJECTED"
    HUMAN_REJECTED = "HUMAN_REJECTED"


class Predicate(str, enum.Enum):
    # Relationships
    DIRECTOR_OF = "DIRECTOR_OF"
    SHAREHOLDER_OF = "SHAREHOLDER_OF"
    REGISTERED_AT = "REGISTERED_AT"
    SAME_AS = "SAME_AS"
    # Derived attributes
    RISK_SCORE = "RISK_SCORE"
    SHELL_INDICATOR = "SHELL_INDICATOR"
    DIRECTOR_VELOCITY = "DIRECTOR_VELOCITY"
    NETWORK_CLUSTER = "NETWORK_CLUSTER"
```

**Acceptance Criteria**:
- [ ] All enums import without error
- [ ] Enum values match specification

### Task 2.2: Create Provenance Model

Create `src/halo/models/provenance.py`:

```python
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import String, Text, ARRAY
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from halo.database import Base
from halo.models.enums import SourceType


class Provenance(Base):
    __tablename__ = "provenances"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    source_type: Mapped[SourceType] = mapped_column(String(30), nullable=False)
    source_id: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(Text)
    source_document_hash: Mapped[Optional[str]] = mapped_column(Text)
    extraction_method: Mapped[str] = mapped_column(Text, nullable=False)
    extraction_timestamp: Mapped[datetime] = mapped_column(nullable=False, default=datetime.utcnow)
    extraction_system_version: Mapped[str] = mapped_column(Text, nullable=False)
    derived_from: Mapped[Optional[list[UUID]]] = mapped_column(ARRAY(PG_UUID(as_uuid=True)))
    derivation_rule: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.utcnow)
```

**Acceptance Criteria**:
- [ ] Model imports without error
- [ ] All fields match specification

### Task 2.3: Create Entity Models

Create `src/halo/models/entity.py`:

```python
from datetime import datetime, date
from typing import Optional
from uuid import UUID, uuid4

from geoalchemy2 import Geography
from sqlalchemy import String, Text, Float, Integer, Boolean, ForeignKey, ARRAY, Index
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from halo.database import Base
from halo.models.enums import EntityType, EntityStatus


class Entity(Base):
    __tablename__ = "entities"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    entity_type: Mapped[EntityType] = mapped_column(String(20), nullable=False)
    canonical_name: Mapped[str] = mapped_column(Text, nullable=False)
    resolution_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    status: Mapped[EntityStatus] = mapped_column(
        String(20), nullable=False, default=EntityStatus.ACTIVE
    )
    merged_into: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("entities.id")
    )
    split_from: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("entities.id")
    )
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.utcnow)
    anonymized_at: Mapped[Optional[datetime]] = mapped_column()

    # Relationships
    identifiers: Mapped[list["EntityIdentifier"]] = relationship(back_populates="entity")

    __table_args__ = (
        Index("idx_entity_type", "entity_type", postgresql_where="status = 'ACTIVE'"),
        Index("idx_entity_status", "status"),
    )


class EntityIdentifier(Base):
    __tablename__ = "entity_identifiers"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    entity_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )
    identifier_type: Mapped[str] = mapped_column(String(30), nullable=False)
    identifier_value: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    provenance_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("provenances.id"), nullable=False
    )
    valid_from: Mapped[Optional[date]] = mapped_column()
    valid_to: Mapped[Optional[date]] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.utcnow)

    # Relationships
    entity: Mapped["Entity"] = relationship(back_populates="identifiers")

    __table_args__ = (
        Index("idx_ident_lookup", "identifier_type", "identifier_value"),
        Index("idx_ident_entity", "entity_id"),
    )


class PersonAttributes(Base):
    __tablename__ = "person_attributes"

    entity_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), primary_key=True
    )
    birth_year: Mapped[Optional[int]] = mapped_column(Integer)
    birth_date: Mapped[Optional[date]] = mapped_column()
    gender: Mapped[Optional[str]] = mapped_column(String(10))
    company_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active_directorship_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    network_cluster_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True))
    risk_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    risk_factors: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text))
    first_seen: Mapped[date] = mapped_column(nullable=False, default=date.today)
    last_activity: Mapped[date] = mapped_column(nullable=False, default=date.today)
    updated_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_person_risk", "risk_score", postgresql_where="risk_score > 0.5"),
    )


class CompanyAttributes(Base):
    __tablename__ = "company_attributes"

    entity_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), primary_key=True
    )
    legal_form: Mapped[Optional[str]] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="UNKNOWN")
    registration_date: Mapped[Optional[date]] = mapped_column()
    dissolution_date: Mapped[Optional[date]] = mapped_column()
    sni_codes: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text))
    sni_primary: Mapped[Optional[str]] = mapped_column(String(10))
    latest_revenue: Mapped[Optional[int]] = mapped_column()
    latest_employees: Mapped[Optional[int]] = mapped_column(Integer)
    latest_assets: Mapped[Optional[int]] = mapped_column()
    financial_year_end: Mapped[Optional[date]] = mapped_column()
    director_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    director_change_velocity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    network_cluster_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True))
    risk_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    risk_factors: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text))
    shell_indicators: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text))
    ownership_opacity_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    last_filing_date: Mapped[Optional[date]] = mapped_column()
    updated_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_company_status", "status"),
        Index("idx_company_sni", "sni_primary"),
        Index("idx_company_risk", "risk_score", postgresql_where="risk_score > 0.5"),
    )


class AddressAttributes(Base):
    __tablename__ = "address_attributes"

    entity_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), primary_key=True
    )
    street: Mapped[str] = mapped_column(Text, nullable=False)
    street_number: Mapped[Optional[str]] = mapped_column(Text)
    postal_code: Mapped[str] = mapped_column(String(10), nullable=False)
    city: Mapped[str] = mapped_column(Text, nullable=False)
    municipality: Mapped[Optional[str]] = mapped_column(String(50))
    coordinates: Mapped[Optional[str]] = mapped_column(Geography("POINT", srid=4326))
    geocode_confidence: Mapped[Optional[float]] = mapped_column(Float)
    vulnerable_area: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    vulnerability_level: Mapped[Optional[str]] = mapped_column(String(20))
    company_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    person_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_registration_hub: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_address_postal", "postal_code"),
        Index("idx_address_vulnerable", "vulnerable_area", postgresql_where="vulnerable_area = TRUE"),
    )
```

**Acceptance Criteria**:
- [ ] All models import without error
- [ ] All indexes defined
- [ ] Foreign keys properly configured

### Task 2.4: Create Fact Model

Create `src/halo/models/fact.py`:

```python
from datetime import datetime, date
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import String, Text, Float, Integer, Boolean, ForeignKey, ARRAY, Index
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from halo.database import Base
from halo.models.enums import FactType, Predicate


class Fact(Base):
    __tablename__ = "facts"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    fact_type: Mapped[FactType] = mapped_column(String(20), nullable=False)
    subject_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("entities.id"), nullable=False
    )
    predicate: Mapped[str] = mapped_column(String(50), nullable=False)
    
    # Value columns
    value_text: Mapped[Optional[str]] = mapped_column(Text)
    value_int: Mapped[Optional[int]] = mapped_column()
    value_float: Mapped[Optional[float]] = mapped_column(Float)
    value_date: Mapped[Optional[date]] = mapped_column()
    value_bool: Mapped[Optional[bool]] = mapped_column(Boolean)
    value_json: Mapped[Optional[dict]] = mapped_column(JSONB)
    
    # Relationship target
    object_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("entities.id")
    )
    relationship_attributes: Mapped[Optional[dict]] = mapped_column(JSONB)
    
    # Temporality
    valid_from: Mapped[date] = mapped_column(nullable=False)
    valid_to: Mapped[Optional[date]] = mapped_column()
    
    # Confidence and provenance
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    provenance_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("provenances.id"), nullable=False
    )
    
    # Lifecycle
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.utcnow)
    superseded_by: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("facts.id")
    )
    superseded_at: Mapped[Optional[datetime]] = mapped_column()
    
    # Derivation
    is_derived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    derivation_rule: Mapped[Optional[str]] = mapped_column(Text)
    derived_from: Mapped[Optional[list[UUID]]] = mapped_column(ARRAY(PG_UUID(as_uuid=True)))

    __table_args__ = (
        Index(
            "idx_fact_subject", "subject_id", "predicate",
            postgresql_where="superseded_by IS NULL"
        ),
        Index(
            "idx_fact_object", "object_id", "predicate",
            postgresql_where="superseded_by IS NULL AND object_id IS NOT NULL"
        ),
        Index(
            "idx_fact_temporal", "valid_from", "valid_to",
            postgresql_where="superseded_by IS NULL"
        ),
        Index(
            "idx_fact_current", "subject_id",
            postgresql_where="superseded_by IS NULL AND valid_to IS NULL"
        ),
    )
```

**Acceptance Criteria**:
- [ ] Model imports without error
- [ ] Partial indexes properly defined

### Task 2.5: Create Mention Model

Create `src/halo/models/mention.py`:

```python
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import String, Text, Float, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from halo.database import Base
from halo.models.enums import EntityType, ResolutionStatus


class Mention(Base):
    __tablename__ = "mentions"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    mention_type: Mapped[EntityType] = mapped_column(String(20), nullable=False)
    surface_form: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_form: Mapped[str] = mapped_column(Text, nullable=False)
    extracted_personnummer: Mapped[Optional[str]] = mapped_column(Text)
    extracted_orgnummer: Mapped[Optional[str]] = mapped_column(Text)
    extracted_attributes: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    provenance_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("provenances.id"), nullable=False
    )
    document_location: Mapped[Optional[str]] = mapped_column(Text)
    resolution_status: Mapped[ResolutionStatus] = mapped_column(
        String(20), nullable=False, default=ResolutionStatus.PENDING
    )
    resolved_to: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("entities.id")
    )
    resolution_confidence: Mapped[Optional[float]] = mapped_column(Float)
    resolution_method: Mapped[Optional[str]] = mapped_column(Text)
    resolved_at: Mapped[Optional[datetime]] = mapped_column()
    resolved_by: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index(
            "idx_mention_pending", "mention_type",
            postgresql_where="resolution_status = 'PENDING'"
        ),
        Index(
            "idx_mention_resolved", "resolved_to",
            postgresql_where="resolved_to IS NOT NULL"
        ),
        Index(
            "idx_mention_pnr", "extracted_personnummer",
            postgresql_where="extracted_personnummer IS NOT NULL"
        ),
        Index(
            "idx_mention_org", "extracted_orgnummer",
            postgresql_where="extracted_orgnummer IS NOT NULL"
        ),
    )


class ResolutionDecision(Base):
    __tablename__ = "resolution_decisions"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    mention_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("mentions.id"), nullable=False
    )
    candidate_entity_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("entities.id"), nullable=False
    )
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)
    feature_scores: Mapped[dict] = mapped_column(JSONB, nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    decision_reason: Mapped[Optional[str]] = mapped_column(Text)
    reviewer_id: Mapped[Optional[str]] = mapped_column(Text)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index(
            "idx_resdec_pending", "decision",
            postgresql_where="decision = 'PENDING_REVIEW'"
        ),
        Index("idx_resdec_mention", "mention_id"),
    )
```

**Acceptance Criteria**:
- [ ] Model imports without error
- [ ] All indexes properly defined

### Task 2.6: Create Audit Model

Create `src/halo/models/audit.py`:

```python
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import String, Text, BigInteger
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB, INET
from sqlalchemy.orm import Mapped, mapped_column

from halo.database import Base


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = {"schema": "audit"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_timestamp: Mapped[datetime] = mapped_column(nullable=False, default=datetime.utcnow)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_id: Mapped[Optional[str]] = mapped_column(Text)
    target_type: Mapped[Optional[str]] = mapped_column(String(30))
    target_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True))
    event_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    request_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True))
    ip_address: Mapped[Optional[str]] = mapped_column(INET)
    user_agent: Mapped[Optional[str]] = mapped_column(Text)


class ErasureRequest(Base):
    __tablename__ = "erasure_requests"
    __table_args__ = {"schema": "audit"}

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    entity_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    request_reference: Mapped[str] = mapped_column(Text, nullable=False)
    requested_at: Mapped[datetime] = mapped_column(nullable=False)
    processed_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.utcnow)
    processor_id: Mapped[str] = mapped_column(Text, nullable=False)
```

**Acceptance Criteria**:
- [ ] Model imports without error
- [ ] Audit schema specified

### Task 2.7: Create Model Index and Alembic Setup

Create `src/halo/models/__init__.py`:

```python
from halo.models.enums import (
    EntityType,
    EntityStatus,
    FactType,
    SourceType,
    ResolutionStatus,
    Predicate,
)
from halo.models.provenance import Provenance
from halo.models.entity import (
    Entity,
    EntityIdentifier,
    PersonAttributes,
    CompanyAttributes,
    AddressAttributes,
)
from halo.models.fact import Fact
from halo.models.mention import Mention, ResolutionDecision
from halo.models.audit import AuditLog, ErasureRequest

__all__ = [
    "EntityType",
    "EntityStatus",
    "FactType",
    "SourceType",
    "ResolutionStatus",
    "Predicate",
    "Provenance",
    "Entity",
    "EntityIdentifier",
    "PersonAttributes",
    "CompanyAttributes",
    "AddressAttributes",
    "Fact",
    "Mention",
    "ResolutionDecision",
    "AuditLog",
    "ErasureRequest",
]
```

Create `alembic.ini`:

```ini
[alembic]
script_location = alembic
prepend_sys_path = .
version_path_separator = os

sqlalchemy.url = postgresql+asyncpg://halo:halo@localhost:5432/halo

[post_write_hooks]
hooks = ruff
ruff.type = exec
ruff.executable = ruff
ruff.options = format REVISION_SCRIPT_FILENAME

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

Create `alembic/env.py`:

```python
import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from halo.database import Base
from halo.models import *  # noqa: F401,F403

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

Run initial migration:

```bash
alembic revision --autogenerate -m "initial schema"
alembic upgrade head
```

**Acceptance Criteria**:
- [ ] `alembic revision --autogenerate` generates migration
- [ ] `alembic upgrade head` creates all tables
- [ ] All tables visible in database

---

## Phase 3: Swedish Utilities (Week 3-4)

### Task 3.1: Implement Personnummer Validation

Create `src/halo/swedish/personnummer.py`:

```python
import re
from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass
class PersonnummerResult:
    valid: bool
    normalized: Optional[str]
    birth_date: Optional[date]
    gender: Optional[str]
    is_samordningsnummer: bool
    error: Optional[str]


def validate_personnummer(pnr: str) -> PersonnummerResult:
    """
    Validate and parse Swedish personnummer.
    
    Accepts formats:
    - YYYYMMDD-XXXX (12 digits with dash)
    - YYYYMMDDXXXX (12 digits)
    - YYMMDD-XXXX (10 digits with dash)
    - YYMMDDXXXX (10 digits)
    """
    # Normalize - remove dashes and spaces
    clean = re.sub(r"[-\s]", "", pnr)
    
    # Handle 10-digit format - determine century
    if len(clean) == 10:
        year = int(clean[0:2])
        current_year = date.today().year % 100
        century = "19" if year > current_year else "20"
        clean = century + clean
    
    if len(clean) != 12:
        return PersonnummerResult(
            valid=False,
            normalized=None,
            birth_date=None,
            gender=None,
            is_samordningsnummer=False,
            error="Invalid length",
        )
    
    # Parse components
    try:
        year = int(clean[0:4])
        month = int(clean[4:6])
        day = int(clean[6:8])
        serial = clean[8:11]
        checksum = int(clean[11])
    except ValueError:
        return PersonnummerResult(
            valid=False,
            normalized=None,
            birth_date=None,
            gender=None,
            is_samordningsnummer=False,
            error="Non-numeric characters",
        )
    
    # Check for samordningsnummer (day > 60)
    is_samordning = day > 60
    actual_day = day - 60 if is_samordning else day
    
    # Validate date
    try:
        birth_date = date(year, month, actual_day)
    except ValueError:
        return PersonnummerResult(
            valid=False,
            normalized=None,
            birth_date=None,
            gender=None,
            is_samordningsnummer=is_samordning,
            error="Invalid date",
        )
    
    # Luhn checksum (on 10-digit portion)
    check_digits = clean[2:11]
    weights = [2, 1, 2, 1, 2, 1, 2, 1, 2]
    
    total = 0
    for digit, weight in zip(check_digits, weights):
        product = int(digit) * weight
        total += product // 10 + product % 10
    
    expected_checksum = (10 - (total % 10)) % 10
    
    if checksum != expected_checksum:
        return PersonnummerResult(
            valid=False,
            normalized=clean,
            birth_date=birth_date,
            gender=None,
            is_samordningsnummer=is_samordning,
            error="Invalid checksum",
        )
    
    # Determine gender (odd = male, even = female)
    gender = "M" if int(serial[2]) % 2 == 1 else "F"
    
    return PersonnummerResult(
        valid=True,
        normalized=clean,
        birth_date=birth_date,
        gender=gender,
        is_samordningsnummer=is_samordning,
        error=None,
    )


def extract_birth_year(pnr: str) -> Optional[int]:
    """Extract birth year from personnummer."""
    result = validate_personnummer(pnr)
    return result.birth_date.year if result.valid and result.birth_date else None
```

Create `tests/test_swedish/test_personnummer.py`:

```python
import pytest
from datetime import date
from halo.swedish.personnummer import validate_personnummer, extract_birth_year


class TestPersonnummer:
    def test_valid_12_digit_with_dash(self):
        # Using a valid test number
        result = validate_personnummer("19811218-9876")
        assert result.valid
        assert result.normalized == "198112189876"
        assert result.birth_date == date(1981, 12, 18)
        
    def test_valid_10_digit(self):
        result = validate_personnummer("8112189876")
        assert result.valid
        assert result.normalized == "198112189876"
        
    def test_invalid_checksum(self):
        result = validate_personnummer("19811218-9875")
        assert not result.valid
        assert result.error and "checksum" in result.error.lower()
        
    def test_invalid_date(self):
        result = validate_personnummer("19811318-9876")
        assert not result.valid
        assert result.error and "date" in result.error.lower()
        
    def test_samordningsnummer(self):
        # Day + 60
        result = validate_personnummer("19811278-9870")
        assert result.is_samordningsnummer
        
    def test_gender_male(self):
        result = validate_personnummer("19811218-9876")
        if result.valid:
            # Check if serial third digit is odd
            serial_third = int(result.normalized[10])
            expected_gender = "M" if serial_third % 2 == 1 else "F"
            assert result.gender == expected_gender
            
    def test_extract_birth_year(self):
        year = extract_birth_year("19811218-9876")
        assert year == 1981
        
    def test_extract_birth_year_invalid(self):
        year = extract_birth_year("invalid")
        assert year is None
```

**Acceptance Criteria**:
- [ ] `pytest tests/test_swedish/test_personnummer.py` passes
- [ ] Valid personnummer returns correct birth date
- [ ] Invalid checksums rejected
- [ ] Samordningsnummer detected correctly

### Task 3.2: Implement Company Name Normalization

Create `src/halo/swedish/company_name.py`:

```python
import re
from typing import Tuple, Optional

import jellyfish

# Legal form patterns
LEGAL_FORMS = {
    r"\bAKTIEBOLAG\b": "AB",
    r"\bAKTIEBOLAGET\b": "AB",
    r"\bHANDELSBOLAG\b": "HB",
    r"\bHANDELSBOLAGET\b": "HB",
    r"\bKOMMANDITBOLAG\b": "KB",
    r"\bKOMMANDITBOLAGET\b": "KB",
    r"\bENSKILD\s*FIRMA\b": "EF",
    r"\bEKONOMISK\s*FÖRENING\b": "EK FÖR",
    r"\bIDEELL\s*FÖRENING\b": "IDEELL FÖR",
    r"\bSTIFTELSE\b": "STIFTELSE",
}

# Status indicators to remove for matching
STATUS_INDICATORS = [
    r"\bI\s*LIKVIDATION\b",
    r"\bI\s*KONKURS\b",
    r"\bUNDER\s*REKONSTRUKTION\b",
    r"\bUNDER\s*AVVECKLING\b",
    r"\(PUBL\)",
    r"\bPUBL\b",
]


def normalize_company_name(name: str) -> Tuple[str, Optional[str]]:
    """
    Normalize Swedish company name for matching.
    
    Returns: (normalized_name, detected_legal_form)
    """
    normalized = name.upper().strip()
    legal_form = None
    
    # Detect and normalize legal form
    for pattern, form in LEGAL_FORMS.items():
        if re.search(pattern, normalized):
            legal_form = form
            normalized = re.sub(pattern, "", normalized)
            break
    
    # Remove trailing "AB" etc if at end
    normalized = re.sub(r"\s+(AB|HB|KB|EF)\s*$", "", normalized)
    
    # Remove status indicators
    for pattern in STATUS_INDICATORS:
        normalized = re.sub(pattern, "", normalized)
    
    # Remove punctuation except &
    normalized = re.sub(r"[^\w\s&]", " ", normalized)
    
    # Normalize whitespace
    normalized = re.sub(r"\s+", " ", normalized).strip()
    
    return normalized, legal_form


def company_name_similarity(name1: str, name2: str) -> float:
    """
    Compute similarity between two company names.
    """
    norm1, _ = normalize_company_name(name1)
    norm2, _ = normalize_company_name(name2)
    
    # Exact normalized match
    if norm1 == norm2:
        return 1.0
    
    # Jaro-Winkler on normalized names
    jw_score = jellyfish.jaro_winkler_similarity(norm1, norm2)
    
    # Token overlap
    tokens1 = set(norm1.split())
    tokens2 = set(norm2.split())
    
    if tokens1 and tokens2:
        jaccard = len(tokens1 & tokens2) / len(tokens1 | tokens2)
    else:
        jaccard = 0.0
    
    # Combined score
    return 0.6 * jw_score + 0.4 * jaccard
```

Create `tests/test_swedish/test_company_name.py`:

```python
import pytest
from halo.swedish.company_name import normalize_company_name, company_name_similarity


class TestCompanyName:
    def test_normalize_aktiebolag(self):
        name, form = normalize_company_name("Test Aktiebolag")
        assert name == "TEST"
        assert form == "AB"
        
    def test_normalize_ab_suffix(self):
        name, form = normalize_company_name("Test AB")
        assert name == "TEST"
        assert form == "AB"
        
    def test_normalize_i_likvidation(self):
        name, _ = normalize_company_name("Test AB i likvidation")
        assert "LIKVIDATION" not in name
        
    def test_normalize_publ(self):
        name, _ = normalize_company_name("Test AB (publ)")
        assert "PUBL" not in name
        
    def test_similarity_exact(self):
        score = company_name_similarity("Test AB", "Test Aktiebolag")
        assert score == 1.0
        
    def test_similarity_similar(self):
        score = company_name_similarity("Test Bygg AB", "Test Byggnad AB")
        assert score > 0.7
        
    def test_similarity_different(self):
        score = company_name_similarity("ABC AB", "XYZ AB")
        assert score < 0.5
```

**Acceptance Criteria**:
- [ ] `pytest tests/test_swedish/test_company_name.py` passes
- [ ] Legal forms detected and normalized
- [ ] Status indicators removed
- [ ] Similarity scores sensible

### Task 3.3: Implement Address Parsing

Create `src/halo/swedish/address.py`:

```python
import re
from dataclasses import dataclass
from typing import Optional

import jellyfish

# Street type normalization
STREET_TYPES = {
    "GATAN": "G",
    "VÄGEN": "V",
    "ALLÉN": "A",
    "STIGEN": "ST",
    "GRÄND": "GR",
    "PLAN": "PL",
    "TORG": "T",
    "BACKE": "B",
    "PLATS": "PL",
}


@dataclass
class ParsedAddress:
    street: str
    street_number: Optional[str]
    entrance: Optional[str]
    postal_code: Optional[str]
    city: Optional[str]
    normalized: str


def parse_swedish_address(address: str) -> ParsedAddress:
    """Parse Swedish address into components."""
    addr = address.upper().strip()
    
    # Extract postal code (5 digits, optional space)
    postal_match = re.search(r"(\d{3})\s?(\d{2})", addr)
    postal_code = None
    city = None
    
    if postal_match:
        postal_code = f"{postal_match.group(1)} {postal_match.group(2)}"
        # City is usually after postal code
        after_postal = addr[postal_match.end():].strip()
        city_match = re.match(r"^([A-ZÅÄÖ\s]+)", after_postal)
        if city_match:
            city = city_match.group(1).strip()
        addr = addr[:postal_match.start()].strip()
    
    # Extract street number with optional entrance
    number_match = re.search(r"(\d+)\s*([A-Z])?(?:\s|,|$)", addr)
    street_number = None
    entrance = None
    
    if number_match:
        street_number = number_match.group(1)
        entrance = number_match.group(2)
        addr = addr[:number_match.start()].strip()
    
    # Remaining is street name
    street = addr.rstrip(",").strip()
    
    # Normalize street name
    for full, abbrev in STREET_TYPES.items():
        street = re.sub(rf"\b{full}\b", abbrev, street)
    
    # Build normalized form
    parts = [street]
    if street_number:
        parts.append(street_number)
        if entrance:
            parts.append(entrance)
    if postal_code:
        parts.append(postal_code)
    if city:
        parts.append(city)
    
    normalized = " ".join(parts)
    
    return ParsedAddress(
        street=street,
        street_number=street_number,
        entrance=entrance,
        postal_code=postal_code,
        city=city,
        normalized=normalized,
    )


def address_similarity(addr1: str, addr2: str) -> float:
    """Compute similarity between two addresses."""
    p1 = parse_swedish_address(addr1)
    p2 = parse_swedish_address(addr2)
    
    # Exact postal code match is strong signal
    postal_match = 1.0 if p1.postal_code == p2.postal_code else 0.0
    
    # Street match
    street_sim = jellyfish.jaro_winkler_similarity(p1.street, p2.street)
    
    # Number match
    number_match = 1.0 if p1.street_number == p2.street_number else 0.0
    
    # Combined score
    return 0.3 * postal_match + 0.5 * street_sim + 0.2 * number_match
```

Create `tests/test_swedish/test_address.py`:

```python
import pytest
from halo.swedish.address import parse_swedish_address, address_similarity


class TestAddress:
    def test_parse_full_address(self):
        result = parse_swedish_address("Storgatan 15, 111 22 Stockholm")
        assert result.street == "STORG"  # Normalized
        assert result.street_number == "15"
        assert result.postal_code == "111 22"
        assert result.city == "STOCKHOLM"
        
    def test_parse_with_entrance(self):
        result = parse_swedish_address("Kungsgatan 5B, 111 43 Stockholm")
        assert result.street_number == "5"
        assert result.entrance == "B"
        
    def test_street_normalization(self):
        result = parse_swedish_address("Storgatan 1")
        assert "GATAN" not in result.street
        
    def test_similarity_same_address(self):
        score = address_similarity(
            "Storgatan 15, 111 22 Stockholm",
            "STORGATAN 15, 11122 STOCKHOLM"
        )
        assert score > 0.9
        
    def test_similarity_different_number(self):
        score = address_similarity(
            "Storgatan 15, 111 22 Stockholm",
            "Storgatan 20, 111 22 Stockholm"
        )
        assert score < 0.9
```

**Acceptance Criteria**:
- [ ] `pytest tests/test_swedish/test_address.py` passes
- [ ] Postal codes extracted correctly
- [ ] Street types normalized
- [ ] Similarity scores sensible

### Task 3.4: Create Swedish Utils Index

Update `src/halo/swedish/__init__.py`:

```python
from halo.swedish.personnummer import (
    PersonnummerResult,
    validate_personnummer,
    extract_birth_year,
)
from halo.swedish.company_name import (
    normalize_company_name,
    company_name_similarity,
)
from halo.swedish.address import (
    ParsedAddress,
    parse_swedish_address,
    address_similarity,
)

__all__ = [
    "PersonnummerResult",
    "validate_personnummer",
    "extract_birth_year",
    "normalize_company_name",
    "company_name_similarity",
    "ParsedAddress",
    "parse_swedish_address",
    "address_similarity",
]
```

**Acceptance Criteria**:
- [ ] All Swedish utilities importable from `halo.swedish`
- [ ] `pytest tests/test_swedish/` all pass

---

## Phase 4: Entity Resolution (Week 5-8)

### Task 4.1: Create Blocking Index

Create `src/halo/resolution/blocking.py`:

```python
from typing import Optional
from uuid import UUID

import metaphone
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from halo.models import Entity, EntityIdentifier, EntityType
from halo.swedish import normalize_company_name


class BlockingIndex:
    """Blocking index for candidate generation in entity resolution."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_candidates(
        self, 
        mention_type: EntityType,
        normalized_name: str,
        extracted_personnummer: Optional[str] = None,
        extracted_orgnummer: Optional[str] = None,
        birth_year: Optional[int] = None,
        postal_code: Optional[str] = None,
    ) -> list[Entity]:
        """Get candidate entities for a mention using multiple blocking strategies."""
        candidates: set[UUID] = set()
        
        # Strategy 1: Exact identifier match (definitive)
        if extracted_personnummer:
            entity = await self._lookup_by_identifier("PERSONNUMMER", extracted_personnummer)
            if entity:
                return [entity]  # Exact match - no need for more
        
        if extracted_orgnummer:
            entity = await self._lookup_by_identifier("ORGANISATIONSNUMMER", extracted_orgnummer)
            if entity:
                return [entity]
        
        # Strategy 2: Phonetic name blocking
        phonetic_key = self._get_phonetic_key(normalized_name)
        phonetic_matches = await self._lookup_by_phonetic(mention_type, phonetic_key)
        candidates.update(e.id for e in phonetic_matches)
        
        # Strategy 3: Name prefix + birth year (persons only)
        if mention_type == EntityType.PERSON and birth_year:
            prefix_key = f"{normalized_name[:4]}_{birth_year}"
            prefix_matches = await self._lookup_by_prefix_year(prefix_key)
            candidates.update(e.id for e in prefix_matches)
        
        # Strategy 4: Postal code prefix (addresses only)
        if mention_type == EntityType.ADDRESS and postal_code:
            postal_matches = await self._lookup_by_postal_prefix(postal_code[:3])
            candidates.update(e.id for e in postal_matches)
        
        # Fetch full entities for candidates
        if not candidates:
            return []
        
        result = await self.db.execute(
            select(Entity).where(
                Entity.id.in_(candidates),
                Entity.status == "ACTIVE",
            )
        )
        return list(result.scalars().all())
    
    async def _lookup_by_identifier(
        self, 
        identifier_type: str, 
        identifier_value: str
    ) -> Optional[Entity]:
        """Lookup entity by exact identifier match."""
        result = await self.db.execute(
            select(Entity)
            .join(EntityIdentifier)
            .where(
                EntityIdentifier.identifier_type == identifier_type,
                EntityIdentifier.identifier_value == identifier_value,
                Entity.status == "ACTIVE",
            )
        )
        return result.scalar_one_or_none()
    
    async def _lookup_by_phonetic(
        self, 
        entity_type: EntityType, 
        phonetic_key: str
    ) -> list[Entity]:
        """Lookup entities by phonetic key similarity."""
        # Use trigram similarity for fuzzy matching
        result = await self.db.execute(
            text("""
                SELECT e.* FROM entities e
                WHERE e.entity_type = :entity_type
                AND e.status = 'ACTIVE'
                AND similarity(e.canonical_name, :name) > 0.3
                ORDER BY similarity(e.canonical_name, :name) DESC
                LIMIT 50
            """),
            {"entity_type": entity_type.value, "name": phonetic_key}
        )
        return list(result.scalars().all())
    
    async def _lookup_by_prefix_year(self, prefix_key: str) -> list[Entity]:
        """Lookup persons by name prefix and birth year."""
        parts = prefix_key.split("_")
        if len(parts) != 2:
            return []
        
        name_prefix, birth_year = parts[0], int(parts[1])
        
        result = await self.db.execute(
            text("""
                SELECT e.* FROM entities e
                JOIN person_attributes pa ON pa.entity_id = e.id
                WHERE e.entity_type = 'PERSON'
                AND e.status = 'ACTIVE'
                AND e.canonical_name ILIKE :prefix
                AND pa.birth_year = :birth_year
                LIMIT 50
            """),
            {"prefix": f"{name_prefix}%", "birth_year": birth_year}
        )
        return list(result.scalars().all())
    
    async def _lookup_by_postal_prefix(self, postal_prefix: str) -> list[Entity]:
        """Lookup addresses by postal code prefix."""
        result = await self.db.execute(
            text("""
                SELECT e.* FROM entities e
                JOIN address_attributes aa ON aa.entity_id = e.id
                WHERE e.entity_type = 'ADDRESS'
                AND e.status = 'ACTIVE'
                AND aa.postal_code LIKE :prefix
                LIMIT 100
            """),
            {"prefix": f"{postal_prefix}%"}
        )
        return list(result.scalars().all())
    
    @staticmethod
    def _get_phonetic_key(name: str) -> str:
        """Generate phonetic key using Double Metaphone."""
        primary, secondary = metaphone.doublemetaphone(name)
        return primary or secondary or name[:4].upper()
```

**Acceptance Criteria**:
- [ ] BlockingIndex class implements all strategies
- [ ] Exact identifier matching returns single entity
- [ ] Phonetic matching returns candidates
- [ ] Results limited to prevent performance issues

### Task 4.2: Create Feature Comparison

Create `src/halo/resolution/comparison.py`:

```python
from dataclasses import dataclass, field
from typing import Optional
from uuid import UUID

import jellyfish
from sqlalchemy.ext.asyncio import AsyncSession

from halo.models import Entity, EntityType, PersonAttributes, CompanyAttributes
from halo.swedish import (
    company_name_similarity,
    address_similarity,
    extract_birth_year,
)


@dataclass
class FeatureScores:
    """Feature scores for entity resolution comparison."""
    identifier_match: float = 0.0
    name_jaro_winkler: float = 0.0
    name_token_jaccard: float = 0.0
    birth_year_match: float = 0.0
    address_similarity: float = 0.0
    network_overlap: float = 0.0


class FeatureComparator:
    """Compute pairwise features for entity resolution."""
    
    # Weights for scoring (no ML yet - rule-based)
    PERSON_WEIGHTS = {
        "identifier_match": 10.0,
        "name_jaro_winkler": 2.0,
        "name_token_jaccard": 1.5,
        "birth_year_match": 1.5,
        "address_similarity": 1.0,
        "network_overlap": 2.5,
    }
    
    COMPANY_WEIGHTS = {
        "identifier_match": 10.0,
        "name_jaro_winkler": 3.0,
        "address_similarity": 1.5,
        "network_overlap": 2.0,
    }
    
    ADDRESS_WEIGHTS = {
        "identifier_match": 10.0,
        "name_jaro_winkler": 2.0,
        "address_similarity": 3.0,
    }
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def compute_features(
        self,
        mention_type: EntityType,
        mention_normalized: str,
        mention_attributes: dict,
        entity: Entity,
    ) -> FeatureScores:
        """Compute all comparison features between mention and entity."""
        if mention_type == EntityType.PERSON:
            return await self._compute_person_features(
                mention_normalized, mention_attributes, entity
            )
        elif mention_type == EntityType.COMPANY:
            return await self._compute_company_features(
                mention_normalized, mention_attributes, entity
            )
        else:
            return await self._compute_address_features(
                mention_normalized, mention_attributes, entity
            )
    
    async def _compute_person_features(
        self,
        mention_normalized: str,
        mention_attributes: dict,
        entity: Entity,
    ) -> FeatureScores:
        scores = FeatureScores()
        
        # Name similarity
        scores.name_jaro_winkler = jellyfish.jaro_winkler_similarity(
            mention_normalized.lower(),
            entity.canonical_name.lower(),
        )
        
        # Token overlap
        mention_tokens = set(mention_normalized.lower().split())
        entity_tokens = set(entity.canonical_name.lower().split())
        if mention_tokens and entity_tokens:
            scores.name_token_jaccard = (
                len(mention_tokens & entity_tokens) / 
                len(mention_tokens | entity_tokens)
            )
        
        # Birth year match
        mention_year = mention_attributes.get("birth_year")
        if mention_year:
            # Get entity birth year from attributes
            entity_year = await self._get_person_birth_year(entity.id)
            if entity_year:
                scores.birth_year_match = 1.0 if mention_year == entity_year else 0.0
        
        return scores
    
    async def _compute_company_features(
        self,
        mention_normalized: str,
        mention_attributes: dict,
        entity: Entity,
    ) -> FeatureScores:
        scores = FeatureScores()
        
        # Name similarity using Swedish company name logic
        scores.name_jaro_winkler = company_name_similarity(
            mention_normalized,
            entity.canonical_name,
        )
        
        # Address similarity if available
        mention_address = mention_attributes.get("address")
        if mention_address:
            entity_address = await self._get_company_address(entity.id)
            if entity_address:
                scores.address_similarity = address_similarity(
                    mention_address, entity_address
                )
        
        return scores
    
    async def _compute_address_features(
        self,
        mention_normalized: str,
        mention_attributes: dict,
        entity: Entity,
    ) -> FeatureScores:
        scores = FeatureScores()
        
        # Address similarity
        scores.address_similarity = address_similarity(
            mention_normalized,
            entity.canonical_name,
        )
        
        return scores
    
    def compute_score(
        self, 
        features: FeatureScores, 
        entity_type: EntityType
    ) -> float:
        """Compute weighted score from features."""
        # Definitive identifier match
        if features.identifier_match == 1.0:
            return 0.99
        
        weights = self._get_weights(entity_type)
        
        total = 0.0
        max_possible = 0.0
        
        for feature_name, weight in weights.items():
            value = getattr(features, feature_name, 0.0)
            total += value * weight
            max_possible += weight
        
        return total / max_possible if max_possible > 0 else 0.0
    
    def _get_weights(self, entity_type: EntityType) -> dict[str, float]:
        if entity_type == EntityType.PERSON:
            return self.PERSON_WEIGHTS
        elif entity_type == EntityType.COMPANY:
            return self.COMPANY_WEIGHTS
        else:
            return self.ADDRESS_WEIGHTS
    
    async def _get_person_birth_year(self, entity_id: UUID) -> Optional[int]:
        from sqlalchemy import select
        result = await self.db.execute(
            select(PersonAttributes.birth_year).where(
                PersonAttributes.entity_id == entity_id
            )
        )
        return result.scalar_one_or_none()
    
    async def _get_company_address(self, entity_id: UUID) -> Optional[str]:
        # TODO: Get address from relationships
        return None
```

**Acceptance Criteria**:
- [ ] FeatureComparator computes all feature types
- [ ] Score computation uses correct weights
- [ ] Identifier match returns 0.99

### Task 4.3: Create Entity Resolver

Create `src/halo/resolution/resolver.py`:

```python
from dataclasses import dataclass
from datetime import datetime, date
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from halo.config import get_settings
from halo.models import (
    Entity,
    EntityType,
    EntityStatus,
    EntityIdentifier,
    Mention,
    ResolutionStatus,
    ResolutionDecision,
    Provenance,
    SourceType,
    Fact,
    FactType,
    PersonAttributes,
    CompanyAttributes,
    AddressAttributes,
)
from halo.resolution.blocking import BlockingIndex
from halo.resolution.comparison import FeatureComparator, FeatureScores

settings = get_settings()


@dataclass
class ResolutionResult:
    mention_id: UUID
    status: ResolutionStatus
    entity_id: Optional[UUID]
    confidence: Optional[float]
    method: str


class EntityResolver:
    """Main entity resolution pipeline."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.blocker = BlockingIndex(db)
        self.comparator = FeatureComparator(db)
    
    async def resolve_mention(self, mention: Mention) -> ResolutionResult:
        """Resolve single mention to entity."""
        # Get thresholds for this mention type
        auto_match_threshold = self._get_auto_match_threshold(mention.mention_type)
        human_review_min = self._get_human_review_min(mention.mention_type)
        
        # Get candidates via blocking
        candidates = await self.blocker.get_candidates(
            mention_type=mention.mention_type,
            normalized_name=mention.normalized_form,
            extracted_personnummer=mention.extracted_personnummer,
            extracted_orgnummer=mention.extracted_orgnummer,
            birth_year=mention.extracted_attributes.get("birth_year"),
            postal_code=mention.extracted_attributes.get("postal_code"),
        )
        
        if not candidates:
            # No candidates - create new entity
            return await self._create_new_entity(mention)
        
        # Score each candidate
        scored: list[tuple[Entity, float, FeatureScores]] = []
        for candidate in candidates:
            features = await self.comparator.compute_features(
                mention_type=mention.mention_type,
                mention_normalized=mention.normalized_form,
                mention_attributes=mention.extracted_attributes,
                entity=candidate,
            )
            score = self.comparator.compute_score(features, mention.mention_type)
            scored.append((candidate, score, features))
        
        # Get best match
        best_candidate, best_score, best_features = max(scored, key=lambda x: x[1])
        
        # Decide based on thresholds
        if best_score >= auto_match_threshold:
            return await self._auto_match(mention, best_candidate, best_score, best_features)
        elif best_score >= human_review_min:
            return await self._queue_for_review(mention, scored)
        else:
            return await self._create_new_entity(mention)
    
    async def _auto_match(
        self,
        mention: Mention,
        entity: Entity,
        score: float,
        features: FeatureScores,
    ) -> ResolutionResult:
        """Auto-match mention to existing entity."""
        # Update mention
        mention.resolution_status = ResolutionStatus.AUTO_MATCHED
        mention.resolved_to = entity.id
        mention.resolution_confidence = score
        mention.resolution_method = "auto_match"
        mention.resolved_at = datetime.utcnow()
        mention.resolved_by = "system"
        
        # Log decision
        decision = ResolutionDecision(
            mention_id=mention.id,
            candidate_entity_id=entity.id,
            overall_score=score,
            feature_scores=self._features_to_dict(features),
            decision="AUTO_MATCH",
            decision_reason=f"Score {score:.3f} >= threshold",
        )
        self.db.add(decision)
        
        return ResolutionResult(
            mention_id=mention.id,
            status=ResolutionStatus.AUTO_MATCHED,
            entity_id=entity.id,
            confidence=score,
            method="auto_match",
        )
    
    async def _queue_for_review(
        self,
        mention: Mention,
        scored: list[tuple[Entity, float, FeatureScores]],
    ) -> ResolutionResult:
        """Queue mention for human review."""
        mention.resolution_status = ResolutionStatus.PENDING
        
        # Log all candidates for review
        for entity, score, features in scored:
            decision = ResolutionDecision(
                mention_id=mention.id,
                candidate_entity_id=entity.id,
                overall_score=score,
                feature_scores=self._features_to_dict(features),
                decision="PENDING_REVIEW",
            )
            self.db.add(decision)
        
        return ResolutionResult(
            mention_id=mention.id,
            status=ResolutionStatus.PENDING,
            entity_id=None,
            confidence=None,
            method="queued_for_review",
        )
    
    async def _create_new_entity(self, mention: Mention) -> ResolutionResult:
        """Create new entity from mention."""
        # Create entity
        entity = Entity(
            entity_type=mention.mention_type,
            canonical_name=mention.normalized_form,
            resolution_confidence=1.0,
            status=EntityStatus.ACTIVE,
        )
        self.db.add(entity)
        await self.db.flush()  # Get entity ID
        
        # Create identifier if available
        if mention.extracted_personnummer:
            identifier = EntityIdentifier(
                entity_id=entity.id,
                identifier_type="PERSONNUMMER",
                identifier_value=mention.extracted_personnummer,
                provenance_id=mention.provenance_id,
            )
            self.db.add(identifier)
        
        if mention.extracted_orgnummer:
            identifier = EntityIdentifier(
                entity_id=entity.id,
                identifier_type="ORGANISATIONSNUMMER",
                identifier_value=mention.extracted_orgnummer,
                provenance_id=mention.provenance_id,
            )
            self.db.add(identifier)
        
        # Create type-specific attributes
        await self._create_entity_attributes(entity, mention)
        
        # Update mention
        mention.resolution_status = ResolutionStatus.AUTO_MATCHED
        mention.resolved_to = entity.id
        mention.resolution_confidence = 1.0
        mention.resolution_method = "new_entity"
        mention.resolved_at = datetime.utcnow()
        mention.resolved_by = "system"
        
        return ResolutionResult(
            mention_id=mention.id,
            status=ResolutionStatus.AUTO_MATCHED,
            entity_id=entity.id,
            confidence=1.0,
            method="new_entity",
        )
    
    async def _create_entity_attributes(self, entity: Entity, mention: Mention):
        """Create type-specific attribute record."""
        if entity.entity_type == EntityType.PERSON:
            attrs = PersonAttributes(
                entity_id=entity.id,
                birth_year=mention.extracted_attributes.get("birth_year"),
                birth_date=mention.extracted_attributes.get("birth_date"),
                gender=mention.extracted_attributes.get("gender"),
                first_seen=date.today(),
                last_activity=date.today(),
            )
            self.db.add(attrs)
        
        elif entity.entity_type == EntityType.COMPANY:
            attrs = CompanyAttributes(
                entity_id=entity.id,
                legal_form=mention.extracted_attributes.get("legal_form"),
                status=mention.extracted_attributes.get("status", "UNKNOWN"),
                registration_date=mention.extracted_attributes.get("registration_date"),
                sni_codes=mention.extracted_attributes.get("sni_codes"),
                sni_primary=mention.extracted_attributes.get("sni_primary"),
            )
            self.db.add(attrs)
        
        elif entity.entity_type == EntityType.ADDRESS:
            attrs = AddressAttributes(
                entity_id=entity.id,
                street=mention.extracted_attributes.get("street", mention.normalized_form),
                street_number=mention.extracted_attributes.get("street_number"),
                postal_code=mention.extracted_attributes.get("postal_code", ""),
                city=mention.extracted_attributes.get("city", ""),
                municipality=mention.extracted_attributes.get("municipality"),
            )
            self.db.add(attrs)
    
    async def resolve_all_pending(self, batch_size: int = 1000) -> int:
        """Process all pending mentions. Returns count processed."""
        total_processed = 0
        
        while True:
            # Get batch of pending mentions
            result = await self.db.execute(
                select(Mention)
                .where(Mention.resolution_status == ResolutionStatus.PENDING)
                .limit(batch_size)
            )
            mentions = list(result.scalars().all())
            
            if not mentions:
                break
            
            for mention in mentions:
                try:
                    await self.resolve_mention(mention)
                    total_processed += 1
                except Exception as e:
                    # Log error but continue
                    print(f"Error resolving mention {mention.id}: {e}")
            
            await self.db.commit()
        
        return total_processed
    
    def _get_auto_match_threshold(self, entity_type: EntityType) -> float:
        if entity_type == EntityType.PERSON:
            return settings.person_auto_match_threshold
        elif entity_type == EntityType.COMPANY:
            return settings.company_auto_match_threshold
        else:
            return settings.address_auto_match_threshold
    
    def _get_human_review_min(self, entity_type: EntityType) -> float:
        if entity_type == EntityType.PERSON:
            return settings.person_human_review_min
        elif entity_type == EntityType.COMPANY:
            return settings.company_human_review_min
        else:
            return settings.address_human_review_min
    
    @staticmethod
    def _features_to_dict(features: FeatureScores) -> dict:
        return {
            "identifier_match": features.identifier_match,
            "name_jaro_winkler": features.name_jaro_winkler,
            "name_token_jaccard": features.name_token_jaccard,
            "birth_year_match": features.birth_year_match,
            "address_similarity": features.address_similarity,
            "network_overlap": features.network_overlap,
        }
```

**Acceptance Criteria**:
- [ ] EntityResolver processes mentions end-to-end
- [ ] Auto-match works above threshold
- [ ] Human review queue populated for uncertain matches
- [ ] New entities created for no-match cases

### Task 4.4: Create Resolution Module Index

Update `src/halo/resolution/__init__.py`:

```python
from halo.resolution.blocking import BlockingIndex
from halo.resolution.comparison import FeatureComparator, FeatureScores
from halo.resolution.resolver import EntityResolver, ResolutionResult

__all__ = [
    "BlockingIndex",
    "FeatureComparator",
    "FeatureScores",
    "EntityResolver",
    "ResolutionResult",
]
```

**Acceptance Criteria**:
- [ ] All resolution components importable
- [ ] Integration test passes end-to-end

---

## Phase 5: Shell Network Detection (Week 9-10)

### Task 5.1: Implement Shell Network Pattern

Create `src/halo/patterns/shell_network.py`:

```python
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class ShellNetworkParams:
    min_companies: int = 3
    max_employees: int = 2
    max_revenue: int = 500000
    include_dissolved: bool = False


@dataclass
class ShellNetworkMatch:
    person_id: UUID
    person_name: str
    companies: list[UUID]
    company_names: list[str]
    risk_score: float
    indicators: list[str]


class ShellNetworkDetector:
    """Detect shell company network patterns."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def detect(self, params: ShellNetworkParams) -> list[ShellNetworkMatch]:
        """
        Find persons directing multiple shell-like companies.
        
        Shell indicators:
        - Low/no employees
        - Low/no revenue
        - Multiple companies per director
        - Rapid director changes
        """
        query = text("""
            WITH director_companies AS (
                SELECT 
                    f.subject_id as person_id,
                    e_person.canonical_name as person_name,
                    f.object_id as company_id,
                    e_company.canonical_name as company_name,
                    ca.status,
                    ca.latest_employees,
                    ca.latest_revenue,
                    ca.shell_indicators
                FROM facts f
                JOIN entities e_person ON e_person.id = f.subject_id
                JOIN entities e_company ON e_company.id = f.object_id
                JOIN company_attributes ca ON ca.entity_id = f.object_id
                WHERE f.predicate = 'DIRECTOR_OF'
                AND f.valid_to IS NULL
                AND f.superseded_by IS NULL
                AND e_person.status = 'ACTIVE'
                AND e_company.status = 'ACTIVE'
                AND (:include_dissolved OR ca.status = 'ACTIVE')
                AND (ca.latest_employees IS NULL OR ca.latest_employees <= :max_employees)
                AND (ca.latest_revenue IS NULL OR ca.latest_revenue <= :max_revenue)
            ),
            person_shells AS (
                SELECT 
                    person_id,
                    person_name,
                    array_agg(company_id) as company_ids,
                    array_agg(company_name) as company_names,
                    array_agg(DISTINCT shell_ind) as all_indicators
                FROM director_companies,
                LATERAL unnest(COALESCE(shell_indicators, ARRAY[]::text[])) as shell_ind
                GROUP BY person_id, person_name
                HAVING count(*) >= :min_companies
            )
            SELECT 
                ps.person_id,
                ps.person_name,
                ps.company_ids,
                ps.company_names,
                ps.all_indicators,
                COALESCE(pa.risk_score, 0.0) as risk_score
            FROM person_shells ps
            LEFT JOIN person_attributes pa ON pa.entity_id = ps.person_id
            ORDER BY array_length(ps.company_ids, 1) DESC, pa.risk_score DESC
        """)
        
        result = await self.db.execute(
            query,
            {
                "min_companies": params.min_companies,
                "max_employees": params.max_employees,
                "max_revenue": params.max_revenue,
                "include_dissolved": params.include_dissolved,
            }
        )
        
        matches = []
        for row in result.mappings():
            matches.append(ShellNetworkMatch(
                person_id=row["person_id"],
                person_name=row["person_name"],
                companies=list(row["company_ids"]) if row["company_ids"] else [],
                company_names=list(row["company_names"]) if row["company_names"] else [],
                risk_score=float(row["risk_score"]),
                indicators=list(row["all_indicators"]) if row["all_indicators"] else [],
            ))
        
        return matches
```

**Acceptance Criteria**:
- [ ] Shell network query executes without error
- [ ] Returns persons with 3+ shell companies
- [ ] Results ordered by company count and risk score

### Task 5.2: Update Patterns API

Update `src/halo/api/patterns.py`:

```python
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from halo.database import get_db
from halo.patterns.shell_network import ShellNetworkDetector, ShellNetworkParams

router = APIRouter(prefix="/patterns", tags=["patterns"])


class ShellNetworkRequest(BaseModel):
    min_companies: int = 3
    max_employees: int = 2
    max_revenue: int = 500000
    include_dissolved: bool = False


class ShellNetworkMatchResponse(BaseModel):
    person_id: UUID
    person_name: str
    companies: list[UUID]
    company_names: list[str]
    risk_score: float
    indicators: list[str]


class ShellNetworkResponse(BaseModel):
    matches: list[ShellNetworkMatchResponse]
    total_matches: int
    execution_time_ms: int


@router.post("/shell-network", response_model=ShellNetworkResponse)
async def detect_shell_networks(
    request: ShellNetworkRequest,
    db: AsyncSession = Depends(get_db),
) -> ShellNetworkResponse:
    """
    Detect shell company network patterns.
    
    Finds persons directing multiple low-activity companies
    that may indicate organized crime involvement.
    """
    import time
    start = time.time()
    
    detector = ShellNetworkDetector(db)
    params = ShellNetworkParams(
        min_companies=request.min_companies,
        max_employees=request.max_employees,
        max_revenue=request.max_revenue,
        include_dissolved=request.include_dissolved,
    )
    
    matches = await detector.detect(params)
    
    execution_time_ms = int((time.time() - start) * 1000)
    
    return ShellNetworkResponse(
        matches=[
            ShellNetworkMatchResponse(
                person_id=m.person_id,
                person_name=m.person_name,
                companies=m.companies,
                company_names=m.company_names,
                risk_score=m.risk_score,
                indicators=m.indicators,
            )
            for m in matches
        ],
        total_matches=len(matches),
        execution_time_ms=execution_time_ms,
    )
```

**Acceptance Criteria**:
- [ ] POST `/patterns/shell-network` returns results
- [ ] Response includes execution time
- [ ] Request parameters validated

---

## Phase 6: Remaining Implementation (Week 11-16)

### Task 6.1: Implement Entities API

Update `src/halo/api/entities.py` with full implementation:

```python
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from uuid import UUID
from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from halo.database import get_db
from halo.models import Entity, EntityIdentifier, EntityType, EntityStatus

router = APIRouter(prefix="/entities", tags=["entities"])


class EntityIdentifierResponse(BaseModel):
    identifier_type: str
    identifier_value: str
    confidence: float


class EntityResponse(BaseModel):
    id: UUID
    entity_type: str
    canonical_name: str
    status: str
    resolution_confidence: float
    identifiers: list[EntityIdentifierResponse]
    attributes: dict
    same_as: list[UUID]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class GraphNode(BaseModel):
    id: UUID
    entity_type: str
    canonical_name: str
    risk_score: Optional[float] = None


class GraphEdge(BaseModel):
    source: UUID
    target: UUID
    predicate: str
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None


class GraphResponse(BaseModel):
    root: UUID
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    truncated: bool
    total_nodes: int


@router.get("/{entity_id}", response_model=EntityResponse)
async def get_entity(
    entity_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> EntityResponse:
    """Get entity by ID. Performance target: <100ms"""
    result = await db.execute(
        select(Entity)
        .options(selectinload(Entity.identifiers))
        .where(Entity.id == entity_id)
    )
    entity = result.scalar_one_or_none()
    
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    
    # Get same-as links
    same_as_result = await db.execute(
        text("""
            SELECT object_id FROM facts 
            WHERE subject_id = :entity_id 
            AND predicate = 'SAME_AS' 
            AND superseded_by IS NULL
        """),
        {"entity_id": entity_id}
    )
    same_as = [row[0] for row in same_as_result]
    
    # Get attributes based on type
    attributes = await _get_entity_attributes(db, entity)
    
    return EntityResponse(
        id=entity.id,
        entity_type=entity.entity_type.value,
        canonical_name=entity.canonical_name,
        status=entity.status.value,
        resolution_confidence=entity.resolution_confidence,
        identifiers=[
            EntityIdentifierResponse(
                identifier_type=i.identifier_type,
                identifier_value=i.identifier_value,
                confidence=i.confidence,
            )
            for i in entity.identifiers
        ],
        attributes=attributes,
        same_as=same_as,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


@router.get("/{entity_id}/relationships", response_model=GraphResponse)
async def get_relationships(
    entity_id: UUID,
    depth: int = Query(default=2, ge=1, le=3),
    predicates: Optional[str] = Query(default=None),
    max_nodes: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> GraphResponse:
    """Get relationship graph from entity. Performance target: <1s for depth=2"""
    
    # Parse predicates
    predicate_list = predicates.split(",") if predicates else None
    predicate_filter = ""
    if predicate_list:
        predicate_filter = f"AND f.predicate IN ({','.join(repr(p) for p in predicate_list)})"
    
    # BFS traversal query
    query = text(f"""
        WITH RECURSIVE graph AS (
            -- Base case: starting entity
            SELECT 
                e.id,
                e.entity_type,
                e.canonical_name,
                NULL::uuid as source_id,
                NULL::text as predicate,
                0 as depth
            FROM entities e
            WHERE e.id = :entity_id
            
            UNION
            
            -- Recursive: follow relationships
            SELECT 
                e2.id,
                e2.entity_type,
                e2.canonical_name,
                g.id as source_id,
                f.predicate,
                g.depth + 1 as depth
            FROM graph g
            JOIN facts f ON (f.subject_id = g.id OR f.object_id = g.id)
            JOIN entities e2 ON (
                CASE WHEN f.subject_id = g.id THEN f.object_id ELSE f.subject_id END = e2.id
            )
            WHERE g.depth < :depth
            AND f.superseded_by IS NULL
            AND f.fact_type = 'RELATIONSHIP'
            AND e2.status = 'ACTIVE'
            {predicate_filter}
        )
        SELECT DISTINCT ON (id) * FROM graph
        LIMIT :max_nodes
    """)
    
    result = await db.execute(
        query,
        {"entity_id": entity_id, "depth": depth, "max_nodes": max_nodes}
    )
    
    nodes = []
    edges = []
    seen_nodes = set()
    
    for row in result.mappings():
        node_id = row["id"]
        if node_id not in seen_nodes:
            seen_nodes.add(node_id)
            nodes.append(GraphNode(
                id=node_id,
                entity_type=row["entity_type"],
                canonical_name=row["canonical_name"],
            ))
        
        if row["source_id"]:
            edges.append(GraphEdge(
                source=row["source_id"],
                target=node_id,
                predicate=row["predicate"],
            ))
    
    return GraphResponse(
        root=entity_id,
        nodes=nodes,
        edges=edges,
        truncated=len(nodes) >= max_nodes,
        total_nodes=len(nodes),
    )


@router.get("/by-identifier")
async def get_by_identifier(
    identifier_type: str,
    identifier_value: str,
    db: AsyncSession = Depends(get_db),
) -> EntityResponse:
    """Lookup entity by identifier. Performance target: <100ms"""
    result = await db.execute(
        select(Entity)
        .join(EntityIdentifier)
        .options(selectinload(Entity.identifiers))
        .where(
            EntityIdentifier.identifier_type == identifier_type,
            EntityIdentifier.identifier_value == identifier_value,
            Entity.status == EntityStatus.ACTIVE,
        )
    )
    entity = result.scalar_one_or_none()
    
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    
    # Reuse get_entity logic
    return await get_entity(entity.id, db)


async def _get_entity_attributes(db: AsyncSession, entity: Entity) -> dict:
    """Get type-specific attributes for entity."""
    if entity.entity_type == EntityType.PERSON:
        from halo.models import PersonAttributes
        result = await db.execute(
            select(PersonAttributes).where(PersonAttributes.entity_id == entity.id)
        )
        attrs = result.scalar_one_or_none()
        if attrs:
            return {
                "birth_year": attrs.birth_year,
                "gender": attrs.gender,
                "company_count": attrs.company_count,
                "risk_score": attrs.risk_score,
                "risk_factors": attrs.risk_factors,
            }
    
    elif entity.entity_type == EntityType.COMPANY:
        from halo.models import CompanyAttributes
        result = await db.execute(
            select(CompanyAttributes).where(CompanyAttributes.entity_id == entity.id)
        )
        attrs = result.scalar_one_or_none()
        if attrs:
            return {
                "legal_form": attrs.legal_form,
                "status": attrs.status,
                "registration_date": str(attrs.registration_date) if attrs.registration_date else None,
                "sni_primary": attrs.sni_primary,
                "latest_revenue": attrs.latest_revenue,
                "latest_employees": attrs.latest_employees,
                "risk_score": attrs.risk_score,
                "shell_indicators": attrs.shell_indicators,
            }
    
    elif entity.entity_type == EntityType.ADDRESS:
        from halo.models import AddressAttributes
        result = await db.execute(
            select(AddressAttributes).where(AddressAttributes.entity_id == entity.id)
        )
        attrs = result.scalar_one_or_none()
        if attrs:
            return {
                "street": attrs.street,
                "street_number": attrs.street_number,
                "postal_code": attrs.postal_code,
                "city": attrs.city,
                "vulnerable_area": attrs.vulnerable_area,
                "company_count": attrs.company_count,
            }
    
    return {}
```

**Acceptance Criteria**:
- [ ] GET `/entities/{id}` returns entity with attributes
- [ ] GET `/entities/{id}/relationships` returns graph
- [ ] GET `/entities/by-identifier` lookups work
- [ ] Performance targets met

### Task 6.2: Implement Resolution API

Update `src/halo/api/resolution.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from uuid import UUID
from datetime import datetime

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from halo.database import get_db
from halo.models import Mention, ResolutionDecision, ResolutionStatus, Entity

router = APIRouter(prefix="/resolution", tags=["resolution"])


class MentionResponse(BaseModel):
    id: UUID
    mention_type: str
    surface_form: str
    normalized_form: str
    extracted_attributes: dict
    resolution_status: str
    created_at: datetime


class CandidateResponse(BaseModel):
    entity_id: UUID
    entity_name: str
    score: float
    feature_scores: dict


class ReviewQueueItem(BaseModel):
    mention: MentionResponse
    candidates: list[CandidateResponse]


class ReviewQueueResponse(BaseModel):
    items: list[ReviewQueueItem]
    total_pending: int


class DecisionRequest(BaseModel):
    mention_id: UUID
    entity_id: Optional[UUID]  # None for reject/new entity
    decision: str  # "MATCH" or "REJECT" or "NEW"


class AccuracyMetrics(BaseModel):
    total_ground_truth: int
    true_positives: int
    false_positives: int
    true_negatives: int
    false_negatives: int
    specificity: float
    sensitivity: float


@router.get("/queue", response_model=ReviewQueueResponse)
async def get_review_queue(
    mention_type: Optional[str] = None,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
) -> ReviewQueueResponse:
    """Get mentions pending human review."""
    
    # Build query
    query = select(Mention).where(
        Mention.resolution_status == ResolutionStatus.PENDING
    )
    if mention_type:
        query = query.where(Mention.mention_type == mention_type)
    query = query.limit(limit)
    
    result = await db.execute(query)
    mentions = list(result.scalars().all())
    
    # Get total pending count
    count_result = await db.execute(
        select(func.count(Mention.id)).where(
            Mention.resolution_status == ResolutionStatus.PENDING
        )
    )
    total_pending = count_result.scalar() or 0
    
    # Build response with candidates
    items = []
    for mention in mentions:
        # Get candidates for this mention
        candidates_result = await db.execute(
            select(ResolutionDecision, Entity)
            .join(Entity, ResolutionDecision.candidate_entity_id == Entity.id)
            .where(
                ResolutionDecision.mention_id == mention.id,
                ResolutionDecision.decision == "PENDING_REVIEW",
            )
            .order_by(ResolutionDecision.overall_score.desc())
        )
        
        candidates = [
            CandidateResponse(
                entity_id=entity.id,
                entity_name=entity.canonical_name,
                score=decision.overall_score,
                feature_scores=decision.feature_scores,
            )
            for decision, entity in candidates_result
        ]
        
        items.append(ReviewQueueItem(
            mention=MentionResponse(
                id=mention.id,
                mention_type=mention.mention_type.value,
                surface_form=mention.surface_form,
                normalized_form=mention.normalized_form,
                extracted_attributes=mention.extracted_attributes,
                resolution_status=mention.resolution_status.value,
                created_at=mention.created_at,
            ),
            candidates=candidates,
        ))
    
    return ReviewQueueResponse(
        items=items,
        total_pending=total_pending,
    )


@router.post("/decide")
async def submit_decision(
    request: DecisionRequest,
    reviewer_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Submit human review decision."""
    # Get mention
    result = await db.execute(
        select(Mention).where(Mention.id == request.mention_id)
    )
    mention = result.scalar_one_or_none()
    
    if not mention:
        raise HTTPException(status_code=404, detail="Mention not found")
    
    if mention.resolution_status != ResolutionStatus.PENDING:
        raise HTTPException(status_code=400, detail="Mention already resolved")
    
    if request.decision == "MATCH" and request.entity_id:
        mention.resolution_status = ResolutionStatus.HUMAN_MATCHED
        mention.resolved_to = request.entity_id
        mention.resolution_method = "human_review"
        mention.resolved_by = reviewer_id
        mention.resolved_at = datetime.utcnow()
        
        # Update decision record
        await db.execute(
            select(ResolutionDecision).where(
                ResolutionDecision.mention_id == request.mention_id,
                ResolutionDecision.candidate_entity_id == request.entity_id,
            )
        )
        
    elif request.decision == "REJECT":
        mention.resolution_status = ResolutionStatus.HUMAN_REJECTED
        mention.resolved_by = reviewer_id
        mention.resolved_at = datetime.utcnow()
        
    elif request.decision == "NEW":
        # Create new entity
        from halo.resolution import EntityResolver
        resolver = EntityResolver(db)
        await resolver._create_new_entity(mention)
        mention.resolution_method = "human_new_entity"
        mention.resolved_by = reviewer_id
    
    await db.commit()
    
    return {"status": "ok", "mention_id": request.mention_id}


@router.get("/accuracy", response_model=AccuracyMetrics)
async def get_accuracy_metrics(
    db: AsyncSession = Depends(get_db),
) -> AccuracyMetrics:
    """Get current resolution accuracy against ground truth."""
    
    # This would query validation_ground_truth table
    # For now, return placeholder
    return AccuracyMetrics(
        total_ground_truth=0,
        true_positives=0,
        false_positives=0,
        true_negatives=0,
        false_negatives=0,
        specificity=0.0,
        sensitivity=0.0,
    )
```

**Acceptance Criteria**:
- [ ] GET `/resolution/queue` returns pending items with candidates
- [ ] POST `/resolution/decide` processes decisions
- [ ] Human review workflow complete

### Task 6.3: Create Initial Load Script

Create `scripts/initial_load.py`:

```python
#!/usr/bin/env python
"""Initial data load script for Halo."""

import asyncio
import click
from datetime import datetime

from halo.database import get_db_session
from halo.resolution import EntityResolver


@click.command()
@click.option("--batch-size", default=1000, help="Batch size for processing")
@click.option("--skip-resolution", is_flag=True, help="Skip entity resolution")
@click.option("--source", type=click.Choice(["bolagsverket", "allabolag", "both"]), default="both")
def main(batch_size: int, skip_resolution: bool, source: str):
    """Run initial data load."""
    asyncio.run(_main(batch_size, skip_resolution, source))


async def _main(batch_size: int, skip_resolution: bool, source: str):
    start_time = datetime.now()
    click.echo(f"Starting initial load at {start_time}")
    
    async with get_db_session() as db:
        # Load data
        if source in ("bolagsverket", "both"):
            click.echo("Loading from Bolagsverket...")
            # TODO: Implement Bolagsverket ingestion
            click.echo("Bolagsverket loading not yet implemented")
        
        if source in ("allabolag", "both"):
            click.echo("Loading from Allabolag...")
            # TODO: Implement Allabolag ingestion
            click.echo("Allabolag loading not yet implemented")
        
        if not skip_resolution:
            click.echo("Running entity resolution...")
            resolver = EntityResolver(db)
            processed = await resolver.resolve_all_pending(batch_size=batch_size)
            click.echo(f"Resolved {processed} mentions")
        
        await db.commit()
    
    end_time = datetime.now()
    duration = end_time - start_time
    click.echo(f"Initial load complete in {duration}")


if __name__ == "__main__":
    main()
```

**Acceptance Criteria**:
- [ ] Script runs without error
- [ ] `--help` shows options
- [ ] Resolution runs if not skipped

### Task 6.4: Create Test Fixtures

Create `tests/conftest.py`:

```python
import pytest
import asyncio
from typing import AsyncGenerator
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

from halo.database import Base
from halo.models import (
    Entity, EntityType, EntityStatus, EntityIdentifier,
    Provenance, SourceType, Mention, ResolutionStatus,
    PersonAttributes, CompanyAttributes,
)


# Test database URL
TEST_DATABASE_URL = "postgresql+asyncpg://halo:halo@localhost:5432/halo_test"


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def engine():
    """Create test database engine."""
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()


@pytest.fixture
async def db(engine) -> AsyncGenerator[AsyncSession, None]:
    """Create test database session."""
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    
    async with async_session() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def sample_provenance(db: AsyncSession) -> Provenance:
    """Create sample provenance for tests."""
    prov = Provenance(
        source_type=SourceType.BOLAGSVERKET_HVD,
        source_id="test-123",
        extraction_method="test",
        extraction_system_version="0.1.0",
    )
    db.add(prov)
    await db.flush()
    return prov


@pytest.fixture
async def sample_person(db: AsyncSession, sample_provenance: Provenance) -> Entity:
    """Create sample person entity."""
    entity = Entity(
        entity_type=EntityType.PERSON,
        canonical_name="Johan Andersson",
        status=EntityStatus.ACTIVE,
    )
    db.add(entity)
    await db.flush()
    
    # Add identifier
    identifier = EntityIdentifier(
        entity_id=entity.id,
        identifier_type="PERSONNUMMER",
        identifier_value="198501011234",
        provenance_id=sample_provenance.id,
    )
    db.add(identifier)
    
    # Add attributes
    attrs = PersonAttributes(
        entity_id=entity.id,
        birth_year=1985,
    )
    db.add(attrs)
    
    await db.flush()
    return entity


@pytest.fixture
async def sample_company(db: AsyncSession, sample_provenance: Provenance) -> Entity:
    """Create sample company entity."""
    entity = Entity(
        entity_type=EntityType.COMPANY,
        canonical_name="Test AB",
        status=EntityStatus.ACTIVE,
    )
    db.add(entity)
    await db.flush()
    
    # Add identifier
    identifier = EntityIdentifier(
        entity_id=entity.id,
        identifier_type="ORGANISATIONSNUMMER",
        identifier_value="5566778899",
        provenance_id=sample_provenance.id,
    )
    db.add(identifier)
    
    # Add attributes
    attrs = CompanyAttributes(
        entity_id=entity.id,
        legal_form="AB",
        status="ACTIVE",
    )
    db.add(attrs)
    
    await db.flush()
    return entity


@pytest.fixture
async def sample_mention(db: AsyncSession, sample_provenance: Provenance) -> Mention:
    """Create sample mention."""
    mention = Mention(
        mention_type=EntityType.PERSON,
        surface_form="Johan Andersson",
        normalized_form="JOHAN ANDERSSON",
        extracted_personnummer="198501011234",
        extracted_attributes={"birth_year": 1985},
        provenance_id=sample_provenance.id,
        resolution_status=ResolutionStatus.PENDING,
    )
    db.add(mention)
    await db.flush()
    return mention
```

**Acceptance Criteria**:
- [ ] Fixtures create test data correctly
- [ ] Database session rolls back after each test
- [ ] `pytest tests/` discovers tests

---

## Final Checklist

Before marking phase complete:

### Infrastructure
- [ ] Docker Compose starts all services
- [ ] Database migrations apply cleanly
- [ ] API starts and responds to health checks

### Models
- [ ] All models create tables
- [ ] Indexes created
- [ ] Foreign keys work

### Swedish Utilities
- [ ] Personnummer validation works
- [ ] Company name normalization works
- [ ] Address parsing works
- [ ] All tests pass

### Entity Resolution
- [ ] Blocking finds candidates
- [ ] Feature comparison scores correctly
- [ ] Auto-match above 0.95 threshold
- [ ] Human review queue populated
- [ ] New entities created

### Patterns
- [ ] Shell network detection returns results
- [ ] Query executes in <10s

### API
- [ ] All endpoints return correct responses
- [ ] Error handling works
- [ ] Performance targets met

### Tests
- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] Coverage >80%

---

## Phase 7: Frontend Foundation (Week 17-18)

### Task 7.1: Initialize Frontend Project

```bash
cd ~/projects/halo
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
```

Install dependencies:

```bash
npm install \
  mapbox-gl \
  @types/mapbox-gl \
  cytoscape \
  @types/cytoscape \
  cytoscape-cola \
  h3-js \
  supercluster \
  @tanstack/react-query \
  zustand \
  react-router-dom \
  axios \
  tailwindcss \
  postcss \
  autoprefixer \
  @radix-ui/react-checkbox \
  @radix-ui/react-slider \
  @radix-ui/react-popover \
  @radix-ui/react-dialog \
  lucide-react \
  recharts \
  clsx \
  tailwind-merge
```

Initialize Tailwind:

```bash
npx tailwindcss init -p
```

**Acceptance Criteria**:
- [ ] `npm run dev` starts Vite dev server
- [ ] React app renders in browser
- [ ] No TypeScript errors

### Task 7.2: Configure Tailwind

Update `tailwind.config.ts`:

```typescript
import type { Config } from 'tailwindcss';

export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        // Risk scale
        'risk-low': '#22c55e',
        'risk-medium': '#eab308',
        'risk-high': '#ef4444',
        'risk-critical': '#dc2626',
        
        // Entity types
        'entity-person': '#3b82f6',
        'entity-company': '#8b5cf6',
        'entity-address': '#06b6d4',
      },
    },
  },
  plugins: [],
} satisfies Config;
```

Update `src/index.css`:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  body {
    @apply bg-gray-900 text-white;
  }
}

/* Mapbox overrides */
.mapboxgl-map {
  font-family: inherit;
}

.mapboxgl-popup-content {
  @apply bg-gray-800 text-white rounded-lg shadow-xl border border-gray-700 p-0;
}

.mapboxgl-popup-tip {
  border-top-color: #1f2937;
}
```

**Acceptance Criteria**:
- [ ] Tailwind classes apply correctly
- [ ] Custom colors available
- [ ] Dark theme applied to body

### Task 7.3: Create Directory Structure

```bash
cd frontend/src
mkdir -p api
mkdir -p components/{common,discovery,investigation,detail,patterns,layout}
mkdir -p stores
mkdir -p hooks
mkdir -p lib
mkdir -p types
```

Create `src/types/entity.ts`:

```typescript
export type EntityType = 'PERSON' | 'COMPANY' | 'ADDRESS';
export type EntityStatus = 'ACTIVE' | 'MERGED' | 'SPLIT' | 'ANONYMIZED';

export interface EntityIdentifier {
  identifier_type: string;
  identifier_value: string;
  confidence: number;
}

export interface Entity {
  id: string;
  entity_type: EntityType;
  canonical_name: string;
  status: EntityStatus;
  resolution_confidence: number;
  identifiers: EntityIdentifier[];
  attributes: Record<string, unknown>;
  same_as: string[];
  created_at: string;
  updated_at: string;
}

export interface PersonAttributes {
  birth_year?: number;
  gender?: string;
  company_count: number;
  risk_score: number;
  risk_factors?: string[];
}

export interface CompanyAttributes {
  legal_form?: string;
  status: string;
  registration_date?: string;
  sni_primary?: string;
  latest_revenue?: number;
  latest_employees?: number;
  risk_score: number;
  shell_indicators?: string[];
}

export interface AddressAttributes {
  street: string;
  street_number?: string;
  postal_code: string;
  city: string;
  vulnerable_area: boolean;
  company_count: number;
}
```

Create `src/types/spatial.ts`:

```typescript
export interface SpatialCluster {
  h3_index: string;
  resolution: number;
  center: [number, number]; // [lng, lat]
  
  entity_count: number;
  company_count: number;
  person_count: number;
  address_count: number;
  
  avg_risk_score: number;
  max_risk_score: number;
  high_risk_count: number;
  
  shell_network_count: number;
  alert_count: number;
  
  bounds: GeoJSON.Polygon;
}

export interface ViewportBounds {
  minLng: number;
  minLat: number;
  maxLng: number;
  maxLat: number;
}

export interface MapViewport {
  center: [number, number];
  zoom: number;
  bounds: ViewportBounds;
}
```

Create `src/types/graph.ts`:

```typescript
export interface GraphNode {
  id: string;
  entity_type: string;
  canonical_name: string;
  risk_score?: number;
}

export interface GraphEdge {
  source: string;
  target: string;
  predicate: string;
  valid_from?: string;
  valid_to?: string;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}
```

Create `src/types/investigation.ts`:

```typescript
export interface Investigation {
  id: string;
  name: string;
  description?: string;
  created_at: string;
  updated_at: string;
  
  entities: InvestigationEntity[];
  positions: Record<string, { x: number; y: number }>;
  visible_predicates: string[];
  time_range?: [string, string];
  evidence: EvidenceItem[];
  notes: InvestigationNote[];
}

export interface InvestigationEntity {
  entity_id: string;
  added_at: string;
  added_by: string;
  added_reason: 'search' | 'expansion' | 'pattern_match' | 'manual';
  pinned: boolean;
}

export interface EvidenceItem {
  id: string;
  entity_id: string;
  fact_ids: string[];
  note?: string;
  added_at: string;
}

export interface InvestigationNote {
  id: string;
  content: string;
  entity_id?: string;
  created_at: string;
}
```

**Acceptance Criteria**:
- [ ] All directories created
- [ ] Type files compile without errors
- [ ] Types importable from `@/types/*`

### Task 7.4: Configure Path Aliases

Update `tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "baseUrl": ".",
    "paths": {
      "@/*": ["./src/*"]
    }
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

Update `vite.config.ts`:

```typescript
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
});
```

**Acceptance Criteria**:
- [ ] `@/` imports work
- [ ] API proxy configured
- [ ] No path resolution errors

### Task 7.5: Create API Client

Create `src/api/client.ts`:

```typescript
import axios from 'axios';

export const api = axios.create({
  baseURL: '/api/v1',
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor for auth (future)
api.interceptors.request.use((config) => {
  // const token = getToken();
  // if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Response interceptor for errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error('API Error:', error.response?.data || error.message);
    return Promise.reject(error);
  }
);
```

Create `src/api/entities.ts`:

```typescript
import { api } from './client';
import type { Entity, GraphData } from '@/types';

export async function getEntity(id: string): Promise<Entity> {
  const response = await api.get(`/entities/${id}`);
  return response.data;
}

export async function getEntityRelationships(
  id: string,
  params?: {
    depth?: number;
    predicates?: string[];
    max_nodes?: number;
  }
): Promise<GraphData> {
  const response = await api.get(`/entities/${id}/relationships`, { params });
  return response.data;
}

export async function getEntityConnections(
  id: string,
  params?: {
    predicates?: string[];
    direction?: 'outgoing' | 'incoming' | 'both';
    limit?: number;
    min_risk?: number;
    exclude?: string[];
  }
): Promise<{ entities: Entity[]; edges: GraphData['edges'] }> {
  const response = await api.get(`/entities/${id}/connections`, {
    params: {
      ...params,
      predicates: params?.predicates?.join(','),
      exclude: params?.exclude?.join(','),
    },
  });
  return response.data;
}

export async function searchEntities(
  query: string,
  params?: {
    entity_type?: string;
    limit?: number;
  }
): Promise<Entity[]> {
  const response = await api.get('/entities/search', {
    params: { q: query, ...params },
  });
  return response.data.results;
}
```

Create `src/api/spatial.ts`:

```typescript
import { api } from './client';
import type { SpatialCluster, Entity, ViewportBounds } from '@/types';

export async function getClusters(
  resolution: number,
  bounds: ViewportBounds,
  params?: {
    min_risk?: number;
  }
): Promise<SpatialCluster[]> {
  const response = await api.get(`/spatial/clusters/${resolution}`, {
    params: {
      bounds: `${bounds.minLng},${bounds.minLat},${bounds.maxLng},${bounds.maxLat}`,
      ...params,
    },
  });
  return response.data;
}

export async function getViewportEntities(
  bounds: ViewportBounds,
  zoom: number,
  params?: {
    limit?: number;
    min_risk?: number;
    entity_types?: string[];
  }
): Promise<Entity[]> {
  const response = await api.get('/spatial/entities/viewport', {
    params: {
      bounds: `${bounds.minLng},${bounds.minLat},${bounds.maxLng},${bounds.maxLat}`,
      zoom,
      ...params,
      entity_types: params?.entity_types?.join(','),
    },
  });
  return response.data.entities;
}

export async function getViewportEdges(
  bounds: ViewportBounds,
  entityIds: string[],
  params?: {
    predicates?: string[];
  }
): Promise<GraphData['edges']> {
  const response = await api.get('/spatial/edges/viewport', {
    params: {
      bounds: `${bounds.minLng},${bounds.minLat},${bounds.maxLng},${bounds.maxLat}`,
      entity_ids: entityIds.join(','),
      predicates: params?.predicates?.join(','),
    },
  });
  return response.data;
}
```

Create `src/api/patterns.ts`:

```typescript
import { api } from './client';

export interface ShellNetworkMatch {
  person_id: string;
  person_name: string;
  companies: string[];
  company_names: string[];
  risk_score: number;
  indicators: string[];
}

export interface ShellNetworkResponse {
  matches: ShellNetworkMatch[];
  total_matches: number;
  execution_time_ms: number;
}

export async function detectShellNetworks(params?: {
  min_companies?: number;
  max_employees?: number;
  max_revenue?: number;
  include_dissolved?: boolean;
}): Promise<ShellNetworkResponse> {
  const response = await api.post('/patterns/shell-network', params);
  return response.data;
}

export interface Alert {
  id: string;
  alert_type: string;
  entity_id: string;
  risk_score: number;
  alert_data: Record<string, unknown>;
  acknowledged: boolean;
  created_at: string;
}

export async function getAlerts(params?: {
  alert_type?: string;
  acknowledged?: boolean;
  limit?: number;
}): Promise<Alert[]> {
  const response = await api.get('/patterns/alerts', { params });
  return response.data.alerts;
}
```

**Acceptance Criteria**:
- [ ] API client exports all functions
- [ ] Types match backend responses
- [ ] No TypeScript errors

### Task 7.6: Create Zustand Stores

Create `src/stores/mapStore.ts`:

```typescript
import { create } from 'zustand';
import type { MapViewport, ViewportBounds } from '@/types';

interface MapState {
  viewport: MapViewport;
  setViewport: (viewport: Partial<MapViewport>) => void;
  
  // Derived
  h3Resolution: number;
  showClusters: boolean;
  showEntities: boolean;
  showEdges: boolean;
}

const CLUSTER_ZOOM_THRESHOLD = 14;
const EDGE_ZOOM_THRESHOLD = 17;

function getH3Resolution(zoom: number): number {
  if (zoom < 5) return 3;
  if (zoom < 8) return 5;
  if (zoom < 11) return 7;
  return 9;
}

export const useMapStore = create<MapState>((set, get) => ({
  viewport: {
    center: [18.0686, 59.3293], // Stockholm
    zoom: 5,
    bounds: { minLng: 10, minLat: 55, maxLng: 25, maxLat: 70 },
  },
  
  setViewport: (update) =>
    set((state) => {
      const viewport = { ...state.viewport, ...update };
      return {
        viewport,
        h3Resolution: getH3Resolution(viewport.zoom),
        showClusters: viewport.zoom < CLUSTER_ZOOM_THRESHOLD,
        showEntities: viewport.zoom >= CLUSTER_ZOOM_THRESHOLD,
        showEdges: viewport.zoom >= EDGE_ZOOM_THRESHOLD,
      };
    }),
  
  h3Resolution: 3,
  showClusters: true,
  showEntities: false,
  showEdges: false,
}));
```

Create `src/stores/selectionStore.ts`:

```typescript
import { create } from 'zustand';

interface SelectionState {
  selectedIds: string[];
  hoveredId: string | null;
  
  setSelected: (ids: string[]) => void;
  addSelected: (id: string) => void;
  removeSelected: (id: string) => void;
  clearSelection: () => void;
  setHovered: (id: string | null) => void;
}

export const useSelectionStore = create<SelectionState>((set) => ({
  selectedIds: [],
  hoveredId: null,
  
  setSelected: (ids) => set({ selectedIds: ids }),
  addSelected: (id) =>
    set((state) => ({
      selectedIds: state.selectedIds.includes(id)
        ? state.selectedIds
        : [...state.selectedIds, id],
    })),
  removeSelected: (id) =>
    set((state) => ({
      selectedIds: state.selectedIds.filter((i) => i !== id),
    })),
  clearSelection: () => set({ selectedIds: [] }),
  setHovered: (id) => set({ hoveredId: id }),
}));
```

Create `src/stores/filterStore.ts`:

```typescript
import { create } from 'zustand';

interface FilterState {
  entityTypes: string[];
  predicates: string[];
  riskRange: [number, number];
  timeRange: [string, string] | null;
  
  setEntityTypes: (types: string[]) => void;
  setPredicates: (predicates: string[]) => void;
  setRiskRange: (range: [number, number]) => void;
  setTimeRange: (range: [string, string] | null) => void;
  resetFilters: () => void;
}

const defaultFilters = {
  entityTypes: ['PERSON', 'COMPANY', 'ADDRESS'],
  predicates: ['DIRECTOR_OF', 'SHAREHOLDER_OF', 'REGISTERED_AT'],
  riskRange: [0, 1] as [number, number],
  timeRange: null,
};

export const useFilterStore = create<FilterState>((set) => ({
  ...defaultFilters,
  
  setEntityTypes: (entityTypes) => set({ entityTypes }),
  setPredicates: (predicates) => set({ predicates }),
  setRiskRange: (riskRange) => set({ riskRange }),
  setTimeRange: (timeRange) => set({ timeRange }),
  resetFilters: () => set(defaultFilters),
}));
```

Create `src/stores/uiStore.ts`:

```typescript
import { create } from 'zustand';

type Mode = 'discovery' | 'investigation';

interface UIState {
  mode: Mode;
  sidebarOpen: boolean;
  detailOpen: boolean;
  
  setMode: (mode: Mode) => void;
  toggleSidebar: () => void;
  toggleDetail: () => void;
  openDetail: () => void;
  closeDetail: () => void;
}

export const useUIStore = create<UIState>((set) => ({
  mode: 'discovery',
  sidebarOpen: true,
  detailOpen: false,
  
  setMode: (mode) => set({ mode }),
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
  toggleDetail: () => set((s) => ({ detailOpen: !s.detailOpen })),
  openDetail: () => set({ detailOpen: true }),
  closeDetail: () => set({ detailOpen: false }),
}));
```

Create `src/stores/investigationStore.ts`:

```typescript
import { create } from 'zustand';
import type { Investigation, InvestigationEntity, GraphEdge, Entity } from '@/types';

interface InvestigationState {
  investigation: Investigation | null;
  entities: Entity[];
  edges: GraphEdge[];
  
  setInvestigation: (investigation: Investigation) => void;
  addEntities: (entities: InvestigationEntity[]) => void;
  removeEntity: (entityId: string) => void;
  addEdges: (edges: GraphEdge[]) => void;
  setPositions: (positions: Record<string, { x: number; y: number }>) => void;
  clearInvestigation: () => void;
}

export const useInvestigationStore = create<InvestigationState>((set) => ({
  investigation: null,
  entities: [],
  edges: [],
  
  setInvestigation: (investigation) => set({ investigation }),
  
  addEntities: (newEntities) =>
    set((state) => ({
      investigation: state.investigation
        ? {
            ...state.investigation,
            entities: [
              ...state.investigation.entities,
              ...newEntities.filter(
                (e) => !state.investigation!.entities.some((ex) => ex.entity_id === e.entity_id)
              ),
            ],
          }
        : null,
    })),
  
  removeEntity: (entityId) =>
    set((state) => ({
      investigation: state.investigation
        ? {
            ...state.investigation,
            entities: state.investigation.entities.filter((e) => e.entity_id !== entityId),
          }
        : null,
      edges: state.edges.filter((e) => e.source !== entityId && e.target !== entityId),
    })),
  
  addEdges: (newEdges) =>
    set((state) => ({
      edges: [
        ...state.edges,
        ...newEdges.filter(
          (e) => !state.edges.some(
            (ex) => ex.source === e.source && ex.target === e.target && ex.predicate === e.predicate
          )
        ),
      ],
    })),
  
  setPositions: (positions) =>
    set((state) => ({
      investigation: state.investigation
        ? { ...state.investigation, positions }
        : null,
    })),
  
  clearInvestigation: () => set({ investigation: null, entities: [], edges: [] }),
}));
```

**Acceptance Criteria**:
- [ ] All stores export correctly
- [ ] State updates work as expected
- [ ] TypeScript types correct

### Task 7.7: Create App Shell

Create `src/components/layout/Header.tsx`:

```typescript
import { Search, Bell, Settings } from 'lucide-react';
import { useUIStore } from '@/stores/uiStore';

export function Header() {
  const { mode, setMode } = useUIStore();
  
  return (
    <header className="h-14 border-b border-gray-700 flex items-center px-4 gap-4">
      {/* Logo */}
      <div className="font-bold text-xl">Halo</div>
      
      {/* Search */}
      <div className="flex-1 max-w-xl">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            placeholder="Search entities..."
            className="w-full bg-gray-800 border border-gray-700 rounded-lg pl-10 pr-4 py-2 text-sm focus:outline-none focus:border-blue-500"
          />
        </div>
      </div>
      
      {/* Mode Switcher */}
      <div className="flex bg-gray-800 rounded-lg p-1">
        <button
          onClick={() => setMode('discovery')}
          className={`px-3 py-1 rounded text-sm ${
            mode === 'discovery' ? 'bg-blue-600' : 'hover:bg-gray-700'
          }`}
        >
          Discovery
        </button>
        <button
          onClick={() => setMode('investigation')}
          className={`px-3 py-1 rounded text-sm ${
            mode === 'investigation' ? 'bg-blue-600' : 'hover:bg-gray-700'
          }`}
        >
          Investigation
        </button>
      </div>
      
      {/* Actions */}
      <div className="flex items-center gap-2">
        <button className="p-2 hover:bg-gray-800 rounded-lg relative">
          <Bell className="w-5 h-5" />
          <span className="absolute top-1 right-1 w-2 h-2 bg-red-500 rounded-full" />
        </button>
        <button className="p-2 hover:bg-gray-800 rounded-lg">
          <Settings className="w-5 h-5" />
        </button>
      </div>
    </header>
  );
}
```

Create `src/components/layout/Sidebar.tsx`:

```typescript
import { useState } from 'react';
import { ChevronRight, Folder, Plus, AlertTriangle, Grid3X3 } from 'lucide-react';

export function Sidebar() {
  return (
    <div className="flex flex-col h-full">
      {/* Investigations */}
      <div className="p-4 border-b border-gray-700">
        <div className="flex items-center justify-between mb-2">
          <h3 className="font-medium text-sm text-gray-400">Investigations</h3>
          <button className="p-1 hover:bg-gray-700 rounded">
            <Plus className="w-4 h-4" />
          </button>
        </div>
        <div className="space-y-1">
          <InvestigationItem name="Malmö Shell Networks" count={23} />
          <InvestigationItem name="Healthcare Infiltration" count={8} />
          <InvestigationItem name="Storgatan 15 Cluster" count={15} />
        </div>
      </div>
      
      {/* Patterns */}
      <div className="p-4 border-b border-gray-700">
        <div className="flex items-center justify-between mb-2">
          <h3 className="font-medium text-sm text-gray-400">Patterns</h3>
        </div>
        <div className="space-y-1">
          <PatternItem name="Shell Networks" count={147} />
          <PatternItem name="High-Risk Directors" count={892} />
        </div>
      </div>
      
      {/* Alerts */}
      <div className="p-4 flex-1">
        <div className="flex items-center justify-between mb-2">
          <h3 className="font-medium text-sm text-gray-400">Alerts</h3>
          <span className="bg-red-600 text-xs px-2 py-0.5 rounded-full">12</span>
        </div>
        <div className="space-y-1">
          <AlertItem type="high_risk" message="New shell network detected" time="2m ago" />
          <AlertItem type="warning" message="Healthcare company in vulnerable area" time="15m ago" />
          <AlertItem type="info" message="Resolution queue: 24 pending" time="1h ago" />
        </div>
      </div>
    </div>
  );
}

function InvestigationItem({ name, count }: { name: string; count: number }) {
  return (
    <button className="w-full flex items-center gap-2 px-2 py-1.5 hover:bg-gray-800 rounded text-sm text-left">
      <Folder className="w-4 h-4 text-gray-400" />
      <span className="flex-1 truncate">{name}</span>
      <span className="text-xs text-gray-500">{count}</span>
      <ChevronRight className="w-4 h-4 text-gray-600" />
    </button>
  );
}

function PatternItem({ name, count }: { name: string; count: number }) {
  return (
    <button className="w-full flex items-center gap-2 px-2 py-1.5 hover:bg-gray-800 rounded text-sm text-left">
      <Grid3X3 className="w-4 h-4 text-gray-400" />
      <span className="flex-1 truncate">{name}</span>
      <span className="text-xs text-gray-500">{count}</span>
    </button>
  );
}

function AlertItem({ type, message, time }: { type: string; message: string; time: string }) {
  const iconColor = type === 'high_risk' ? 'text-red-500' : type === 'warning' ? 'text-yellow-500' : 'text-blue-500';
  
  return (
    <button className="w-full flex items-start gap-2 px-2 py-1.5 hover:bg-gray-800 rounded text-sm text-left">
      <AlertTriangle className={`w-4 h-4 mt-0.5 ${iconColor}`} />
      <div className="flex-1 min-w-0">
        <p className="truncate">{message}</p>
        <p className="text-xs text-gray-500">{time}</p>
      </div>
    </button>
  );
}
```

Create `src/components/layout/AppShell.tsx`:

```typescript
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useUIStore } from '@/stores/uiStore';
import { Header } from './Header';
import { Sidebar } from './Sidebar';
import { FilterPanel } from '../common/FilterPanel';
import { DetailPanel } from '../detail/DetailPanel';

// Lazy load main views
import { DiscoveryMap } from '../discovery/DiscoveryMap';
import { InvestigationWorkspace } from '../investigation/InvestigationWorkspace';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30000,
      refetchOnWindowFocus: false,
    },
  },
});

export function AppShell() {
  const { mode, sidebarOpen, detailOpen } = useUIStore();
  
  return (
    <QueryClientProvider client={queryClient}>
      <div className="h-screen flex flex-col">
        <Header />
        
        <div className="flex-1 flex overflow-hidden">
          {/* Left Sidebar */}
          {sidebarOpen && (
            <aside className="w-64 border-r border-gray-700 overflow-y-auto">
              <Sidebar />
            </aside>
          )}
          
          {/* Main Content */}
          <main className="flex-1 relative">
            {mode === 'discovery' ? (
              <DiscoveryMap />
            ) : (
              <InvestigationWorkspace />
            )}
          </main>
          
          {/* Right Panel */}
          <aside className="w-80 border-l border-gray-700 flex flex-col overflow-hidden">
            <div className="flex-shrink-0 border-b border-gray-700">
              <FilterPanel />
            </div>
            {detailOpen && (
              <div className="flex-1 overflow-y-auto">
                <DetailPanel />
              </div>
            )}
          </aside>
        </div>
      </div>
    </QueryClientProvider>
  );
}
```

Create placeholder components:

`src/components/common/FilterPanel.tsx`:
```typescript
export function FilterPanel() {
  return (
    <div className="p-4">
      <h3 className="font-medium mb-4">Filters</h3>
      <p className="text-sm text-gray-400">Filter panel placeholder</p>
    </div>
  );
}
```

`src/components/detail/DetailPanel.tsx`:
```typescript
export function DetailPanel() {
  return (
    <div className="p-4">
      <h3 className="font-medium mb-4">Details</h3>
      <p className="text-sm text-gray-400">Select an entity to view details</p>
    </div>
  );
}
```

`src/components/discovery/DiscoveryMap.tsx`:
```typescript
export function DiscoveryMap() {
  return (
    <div className="w-full h-full flex items-center justify-center bg-gray-800">
      <p className="text-gray-400">Map loading...</p>
    </div>
  );
}
```

`src/components/investigation/InvestigationWorkspace.tsx`:
```typescript
export function InvestigationWorkspace() {
  return (
    <div className="w-full h-full flex items-center justify-center bg-gray-800">
      <p className="text-gray-400">No investigation open</p>
    </div>
  );
}
```

Update `src/App.tsx`:

```typescript
import { AppShell } from '@/components/layout/AppShell';

export default function App() {
  return <AppShell />;
}
```

**Acceptance Criteria**:
- [ ] App renders with header, sidebar, main area, right panel
- [ ] Mode switching toggles between discovery/investigation
- [ ] Layout responsive to panel toggles

---

## Phase 8: Discovery Map (Week 19-20)

### Task 8.1: Implement Mapbox Integration

Update `src/components/discovery/DiscoveryMap.tsx`:

```typescript
import { useEffect, useRef, useCallback } from 'react';
import mapboxgl from 'mapbox-gl';
import 'mapbox-gl/dist/mapbox-gl.css';
import { useMapStore } from '@/stores/mapStore';

// Set your Mapbox token
mapboxgl.accessToken = import.meta.env.VITE_MAPBOX_TOKEN || '';

export function DiscoveryMap() {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<mapboxgl.Map | null>(null);
  
  const { viewport, setViewport } = useMapStore();
  
  // Initialize map
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    
    const map = new mapboxgl.Map({
      container: containerRef.current,
      style: 'mapbox://styles/mapbox/dark-v11',
      center: viewport.center,
      zoom: viewport.zoom,
      minZoom: 3,
      maxZoom: 20,
    });
    
    mapRef.current = map;
    
    // Add navigation controls
    map.addControl(new mapboxgl.NavigationControl(), 'top-right');
    
    // Update store on move
    map.on('moveend', () => {
      const center = map.getCenter();
      const bounds = map.getBounds();
      
      setViewport({
        center: [center.lng, center.lat],
        zoom: map.getZoom(),
        bounds: {
          minLng: bounds.getWest(),
          minLat: bounds.getSouth(),
          maxLng: bounds.getEast(),
          maxLat: bounds.getNorth(),
        },
      });
    });
    
    // Initial viewport update
    map.once('load', () => {
      const bounds = map.getBounds();
      setViewport({
        bounds: {
          minLng: bounds.getWest(),
          minLat: bounds.getSouth(),
          maxLng: bounds.getEast(),
          maxLat: bounds.getNorth(),
        },
      });
    });
    
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);
  
  return (
    <div ref={containerRef} className="w-full h-full" />
  );
}
```

Add to `.env`:

```
VITE_MAPBOX_TOKEN=your_mapbox_token_here
```

**Acceptance Criteria**:
- [ ] Map renders with dark style
- [ ] Navigation controls visible
- [ ] Viewport state updates on pan/zoom

### Task 8.2: Add Cluster Layer

Create `src/hooks/useSpatialClusters.ts`:

```typescript
import { useQuery } from '@tanstack/react-query';
import { getClusters } from '@/api/spatial';
import type { ViewportBounds } from '@/types';

export function useSpatialClusters({
  resolution,
  bounds,
  minRisk = 0,
  enabled = true,
}: {
  resolution: number;
  bounds: ViewportBounds;
  minRisk?: number;
  enabled?: boolean;
}) {
  return useQuery({
    queryKey: ['clusters', resolution, bounds, minRisk],
    queryFn: () => getClusters(resolution, bounds, { min_risk: minRisk }),
    enabled,
    staleTime: 60000, // 1 minute
  });
}
```

Create `src/components/discovery/ClusterLayer.tsx`:

```typescript
import { useEffect } from 'react';
import type mapboxgl from 'mapbox-gl';
import type { SpatialCluster } from '@/types';
import { riskColor } from '@/lib/colors';

interface ClusterLayerProps {
  map: mapboxgl.Map;
  clusters: SpatialCluster[];
}

export function ClusterLayer({ map, clusters }: ClusterLayerProps) {
  useEffect(() => {
    // Remove existing layers/sources
    if (map.getLayer('clusters-fill')) map.removeLayer('clusters-fill');
    if (map.getLayer('clusters-outline')) map.removeLayer('clusters-outline');
    if (map.getLayer('clusters-label')) map.removeLayer('clusters-label');
    if (map.getSource('clusters')) map.removeSource('clusters');
    
    if (clusters.length === 0) return;
    
    // Create GeoJSON from clusters
    const geojson: GeoJSON.FeatureCollection = {
      type: 'FeatureCollection',
      features: clusters.map((c) => ({
        type: 'Feature',
        properties: {
          h3_index: c.h3_index,
          entity_count: c.entity_count,
          avg_risk_score: c.avg_risk_score,
          high_risk_count: c.high_risk_count,
        },
        geometry: c.bounds,
      })),
    };
    
    // Add source
    map.addSource('clusters', {
      type: 'geojson',
      data: geojson,
    });
    
    // Fill layer
    map.addLayer({
      id: 'clusters-fill',
      type: 'fill',
      source: 'clusters',
      paint: {
        'fill-color': [
          'interpolate',
          ['linear'],
          ['get', 'avg_risk_score'],
          0, '#22c55e',
          0.3, '#eab308',
          0.6, '#ef4444',
          1, '#dc2626',
        ],
        'fill-opacity': 0.6,
      },
    });
    
    // Outline layer
    map.addLayer({
      id: 'clusters-outline',
      type: 'line',
      source: 'clusters',
      paint: {
        'line-color': '#ffffff',
        'line-width': 1,
        'line-opacity': 0.3,
      },
    });
    
    // Label layer
    map.addLayer({
      id: 'clusters-label',
      type: 'symbol',
      source: 'clusters',
      layout: {
        'text-field': ['get', 'entity_count'],
        'text-size': 12,
        'text-allow-overlap': false,
      },
      paint: {
        'text-color': '#ffffff',
        'text-halo-color': '#000000',
        'text-halo-width': 1,
      },
    });
    
    // Click handler
    map.on('click', 'clusters-fill', (e) => {
      if (e.features?.[0]) {
        const feature = e.features[0];
        // Zoom in on click
        map.flyTo({
          center: e.lngLat,
          zoom: map.getZoom() + 2,
        });
      }
    });
    
    // Cursor
    map.on('mouseenter', 'clusters-fill', () => {
      map.getCanvas().style.cursor = 'pointer';
    });
    map.on('mouseleave', 'clusters-fill', () => {
      map.getCanvas().style.cursor = '';
    });
    
  }, [map, clusters]);
  
  return null;
}
```

Create `src/lib/colors.ts`:

```typescript
export function riskColor(score: number): string {
  if (score < 0.3) return '#22c55e'; // green
  if (score < 0.6) return '#eab308'; // yellow
  if (score < 0.8) return '#ef4444'; // red
  return '#dc2626'; // dark red
}

export function entityTypeColor(type: string): string {
  switch (type) {
    case 'PERSON':
      return '#3b82f6'; // blue
    case 'COMPANY':
      return '#8b5cf6'; // purple
    case 'ADDRESS':
      return '#06b6d4'; // cyan
    default:
      return '#6b7280'; // gray
  }
}
```

**Acceptance Criteria**:
- [ ] Clusters render as colored hexagons
- [ ] Colors reflect risk scores
- [ ] Click zooms in
- [ ] Labels show entity counts

### Task 8.3: Add Entity Layer

Create `src/hooks/useViewportEntities.ts`:

```typescript
import { useQuery } from '@tanstack/react-query';
import { getViewportEntities } from '@/api/spatial';
import type { ViewportBounds } from '@/types';

export function useViewportEntities({
  bounds,
  zoom,
  entityTypes,
  minRisk = 0,
  enabled = true,
}: {
  bounds: ViewportBounds;
  zoom: number;
  entityTypes?: string[];
  minRisk?: number;
  enabled?: boolean;
}) {
  return useQuery({
    queryKey: ['viewport-entities', bounds, zoom, entityTypes, minRisk],
    queryFn: () => getViewportEntities(bounds, zoom, { entity_types: entityTypes, min_risk: minRisk }),
    enabled,
    staleTime: 30000,
  });
}
```

Create `src/components/discovery/EntityLayer.tsx`:

```typescript
import { useEffect } from 'react';
import type mapboxgl from 'mapbox-gl';
import type { Entity } from '@/types';
import { useSelectionStore } from '@/stores/selectionStore';
import { useUIStore } from '@/stores/uiStore';

interface EntityLayerProps {
  map: mapboxgl.Map;
  entities: Entity[];
}

export function EntityLayer({ map, entities }: EntityLayerProps) {
  const { setSelected } = useSelectionStore();
  const { openDetail } = useUIStore();
  
  useEffect(() => {
    // Remove existing
    if (map.getLayer('entities')) map.removeLayer('entities');
    if (map.getSource('entities')) map.removeSource('entities');
    
    if (entities.length === 0) return;
    
    // Create GeoJSON from entities
    const geojson: GeoJSON.FeatureCollection = {
      type: 'FeatureCollection',
      features: entities
        .filter((e) => e.attributes?.coordinates)
        .map((e) => ({
          type: 'Feature',
          properties: {
            id: e.id,
            name: e.canonical_name,
            type: e.entity_type,
            risk_score: e.attributes?.risk_score ?? 0,
          },
          geometry: {
            type: 'Point',
            coordinates: e.attributes.coordinates as [number, number],
          },
        })),
    };
    
    map.addSource('entities', {
      type: 'geojson',
      data: geojson,
    });
    
    map.addLayer({
      id: 'entities',
      type: 'circle',
      source: 'entities',
      paint: {
        'circle-radius': [
          'interpolate',
          ['linear'],
          ['zoom'],
          14, 4,
          18, 8,
        ],
        'circle-color': [
          'match',
          ['get', 'type'],
          'PERSON', '#3b82f6',
          'COMPANY', '#8b5cf6',
          'ADDRESS', '#06b6d4',
          '#6b7280',
        ],
        'circle-stroke-color': [
          'interpolate',
          ['linear'],
          ['get', 'risk_score'],
          0, '#22c55e',
          0.5, '#eab308',
          1, '#ef4444',
        ],
        'circle-stroke-width': 2,
      },
    });
    
    // Click handler
    map.on('click', 'entities', (e) => {
      if (e.features?.[0]) {
        const id = e.features[0].properties?.id;
        if (id) {
          setSelected([id]);
          openDetail();
        }
      }
    });
    
    // Cursor
    map.on('mouseenter', 'entities', () => {
      map.getCanvas().style.cursor = 'pointer';
    });
    map.on('mouseleave', 'entities', () => {
      map.getCanvas().style.cursor = '';
    });
    
  }, [map, entities]);
  
  return null;
}
```

**Acceptance Criteria**:
- [ ] Entity points render at high zoom
- [ ] Colors indicate entity type
- [ ] Stroke indicates risk
- [ ] Click selects entity and opens detail

### Task 8.4: Integrate Layers in Map

Update `src/components/discovery/DiscoveryMap.tsx`:

```typescript
import { useEffect, useRef } from 'react';
import mapboxgl from 'mapbox-gl';
import 'mapbox-gl/dist/mapbox-gl.css';
import { useMapStore } from '@/stores/mapStore';
import { useFilterStore } from '@/stores/filterStore';
import { useSpatialClusters } from '@/hooks/useSpatialClusters';
import { useViewportEntities } from '@/hooks/useViewportEntities';
import { ClusterLayer } from './ClusterLayer';
import { EntityLayer } from './EntityLayer';

mapboxgl.accessToken = import.meta.env.VITE_MAPBOX_TOKEN || '';

export function DiscoveryMap() {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<mapboxgl.Map | null>(null);
  
  const { viewport, setViewport, h3Resolution, showClusters, showEntities } = useMapStore();
  const { entityTypes, riskRange } = useFilterStore();
  
  // Fetch data based on zoom level
  const { data: clusters } = useSpatialClusters({
    resolution: h3Resolution,
    bounds: viewport.bounds,
    minRisk: riskRange[0],
    enabled: showClusters,
  });
  
  const { data: entities } = useViewportEntities({
    bounds: viewport.bounds,
    zoom: viewport.zoom,
    entityTypes,
    minRisk: riskRange[0],
    enabled: showEntities,
  });
  
  // Initialize map
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    
    const map = new mapboxgl.Map({
      container: containerRef.current,
      style: 'mapbox://styles/mapbox/dark-v11',
      center: viewport.center,
      zoom: viewport.zoom,
      minZoom: 3,
      maxZoom: 20,
    });
    
    mapRef.current = map;
    
    map.addControl(new mapboxgl.NavigationControl(), 'top-right');
    
    map.on('moveend', () => {
      const center = map.getCenter();
      const bounds = map.getBounds();
      
      setViewport({
        center: [center.lng, center.lat],
        zoom: map.getZoom(),
        bounds: {
          minLng: bounds.getWest(),
          minLat: bounds.getSouth(),
          maxLng: bounds.getEast(),
          maxLat: bounds.getNorth(),
        },
      });
    });
    
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);
  
  return (
    <div ref={containerRef} className="w-full h-full">
      {mapRef.current && (
        <>
          {showClusters && clusters && (
            <ClusterLayer map={mapRef.current} clusters={clusters} />
          )}
          {showEntities && entities && (
            <EntityLayer map={mapRef.current} entities={entities} />
          )}
        </>
      )}
    </div>
  );
}
```

**Acceptance Criteria**:
- [ ] Clusters show at low zoom
- [ ] Entities show at high zoom
- [ ] Transitions smoothly between levels
- [ ] Filters affect displayed data

---

## Phase 9: Investigation Workspace (Week 21-22)

### Task 9.1: Implement Cytoscape Graph

Update `src/components/investigation/InvestigationWorkspace.tsx`:

```typescript
import { useEffect, useRef } from 'react';
import cytoscape from 'cytoscape';
import cola from 'cytoscape-cola';
import { useInvestigationStore } from '@/stores/investigationStore';
import { useSelectionStore } from '@/stores/selectionStore';
import { graphStyles } from './graphStyles';

cytoscape.use(cola);

export function InvestigationWorkspace() {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<cytoscape.Core | null>(null);
  
  const { investigation, entities, edges, setPositions } = useInvestigationStore();
  const { selectedIds, setSelected } = useSelectionStore();
  
  // Initialize Cytoscape
  useEffect(() => {
    if (!containerRef.current) return;
    
    cyRef.current = cytoscape({
      container: containerRef.current,
      style: graphStyles,
      layout: { name: 'preset' },
      minZoom: 0.1,
      maxZoom: 3,
      wheelSensitivity: 0.3,
    });
    
    // Selection handler
    cyRef.current.on('tap', 'node', (e) => {
      setSelected([e.target.id()]);
    });
    
    // Background click clears selection
    cyRef.current.on('tap', (e) => {
      if (e.target === cyRef.current) {
        setSelected([]);
      }
    });
    
    // Position persistence
    cyRef.current.on('dragfree', 'node', (e) => {
      const positions: Record<string, { x: number; y: number }> = {};
      cyRef.current!.nodes().forEach((node) => {
        positions[node.id()] = node.position();
      });
      setPositions(positions);
    });
    
    return () => {
      cyRef.current?.destroy();
      cyRef.current = null;
    };
  }, []);
  
  // Update graph data
  useEffect(() => {
    if (!cyRef.current || !investigation) return;
    
    const cy = cyRef.current;
    
    // Build nodes
    const nodes = entities.map((e) => ({
      data: {
        id: e.id,
        label: e.canonical_name,
        type: e.entity_type,
        riskScore: e.attributes?.risk_score ?? 0,
      },
      position: investigation.positions[e.id],
    }));
    
    // Build edges
    const edgeElements = edges.map((e) => ({
      data: {
        id: `${e.source}-${e.predicate}-${e.target}`,
        source: e.source,
        target: e.target,
        label: e.predicate.replace('_', ' '),
      },
    }));
    
    // Update graph
    cy.json({ elements: { nodes, edges: edgeElements } });
    
    // Layout nodes without positions
    const noPosition = nodes.filter((n) => !n.position);
    if (noPosition.length > 0 && nodes.length > 1) {
      cy.layout({
        name: 'cola',
        animate: true,
        randomize: false,
        fit: false,
        nodeSpacing: 80,
        edgeLength: 150,
      }).run();
    }
  }, [investigation, entities, edges]);
  
  // Highlight selection
  useEffect(() => {
    if (!cyRef.current) return;
    
    cyRef.current.nodes().removeClass('selected');
    selectedIds.forEach((id) => {
      cyRef.current?.$id(id).addClass('selected');
    });
  }, [selectedIds]);
  
  if (!investigation) {
    return (
      <div className="w-full h-full flex items-center justify-center text-gray-400">
        <div className="text-center">
          <p className="text-lg mb-2">No investigation open</p>
          <p className="text-sm">Select an entity from the map or create a new investigation</p>
        </div>
      </div>
    );
  }
  
  return (
    <div className="w-full h-full relative">
      <div ref={containerRef} className="w-full h-full" />
      
      {/* Toolbar */}
      <div className="absolute top-4 left-4 flex gap-2">
        <button className="px-3 py-1.5 bg-gray-800 hover:bg-gray-700 rounded text-sm">
          Auto Layout
        </button>
        <button className="px-3 py-1.5 bg-gray-800 hover:bg-gray-700 rounded text-sm">
          Fit View
        </button>
      </div>
    </div>
  );
}
```

Create `src/components/investigation/graphStyles.ts`:

```typescript
import type { Stylesheet } from 'cytoscape';
import { riskColor, entityTypeColor } from '@/lib/colors';

export const graphStyles: Stylesheet[] = [
  // Nodes
  {
    selector: 'node',
    style: {
      label: 'data(label)',
      'text-valign': 'bottom',
      'text-margin-y': 8,
      'font-size': 11,
      color: '#e5e7eb',
      'text-outline-color': '#111827',
      'text-outline-width': 2,
      width: 40,
      height: 40,
      'border-width': 3,
      'border-color': (ele) => riskColor(ele.data('riskScore') ?? 0),
    },
  },
  {
    selector: 'node[type="PERSON"]',
    style: {
      shape: 'ellipse',
      'background-color': '#3b82f6',
    },
  },
  {
    selector: 'node[type="COMPANY"]',
    style: {
      shape: 'round-rectangle',
      'background-color': '#8b5cf6',
    },
  },
  {
    selector: 'node[type="ADDRESS"]',
    style: {
      shape: 'diamond',
      'background-color': '#06b6d4',
    },
  },
  {
    selector: 'node.selected',
    style: {
      'border-color': '#ffffff',
      'border-width': 4,
      'box-shadow': '0 0 10px #3b82f6',
    },
  },
  {
    selector: 'node:active',
    style: {
      'overlay-opacity': 0,
    },
  },
  
  // Edges
  {
    selector: 'edge',
    style: {
      width: 1.5,
      'line-color': '#4b5563',
      'target-arrow-color': '#4b5563',
      'target-arrow-shape': 'triangle',
      'arrow-scale': 0.8,
      'curve-style': 'bezier',
      label: 'data(label)',
      'font-size': 9,
      color: '#9ca3af',
      'text-rotation': 'autorotate',
      'text-margin-y': -10,
    },
  },
  {
    selector: 'edge:selected',
    style: {
      'line-color': '#3b82f6',
      'target-arrow-color': '#3b82f6',
      width: 2,
    },
  },
];
```

**Acceptance Criteria**:
- [ ] Graph renders with nodes and edges
- [ ] Nodes styled by entity type
- [ ] Edges show relationship labels
- [ ] Selection highlights work
- [ ] Cola layout positions nodes

### Task 9.2: Implement Progressive Expansion

Create `src/hooks/useGraphExpansion.ts`:

```typescript
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useInvestigationStore } from '@/stores/investigationStore';
import { getEntityConnections } from '@/api/entities';

interface ExpandOptions {
  entityId: string;
  predicates?: string[];
  direction?: 'outgoing' | 'incoming' | 'both';
  limit?: number;
  minRisk?: number;
}

export function useGraphExpansion() {
  const queryClient = useQueryClient();
  const { investigation, addEntities, addEdges } = useInvestigationStore();
  
  return useMutation({
    mutationFn: async (options: ExpandOptions) => {
      const excludeIds = investigation?.entities.map((e) => e.entity_id) ?? [];
      
      const result = await getEntityConnections(options.entityId, {
        predicates: options.predicates,
        direction: options.direction ?? 'both',
        limit: options.limit ?? 10,
        min_risk: options.minRisk ?? 0,
        exclude: excludeIds,
      });
      
      return result;
    },
    onSuccess: (data, options) => {
      // Add new entities to investigation
      const newEntities = data.entities.map((e) => ({
        entity_id: e.id,
        added_at: new Date().toISOString(),
        added_by: 'user',
        added_reason: 'expansion' as const,
        pinned: false,
      }));
      
      addEntities(newEntities);
      addEdges(data.edges);
      
      // Invalidate entity queries for new entities
      data.entities.forEach((e) => {
        queryClient.invalidateQueries({ queryKey: ['entity', e.id] });
      });
    },
  });
}
```

Add expansion button to node context menu or detail panel:

```typescript
// In DetailPanel or as a context menu
function ExpandButton({ entityId }: { entityId: string }) {
  const { mutate: expand, isPending } = useGraphExpansion();
  
  return (
    <button
      onClick={() => expand({ entityId, limit: 10 })}
      disabled={isPending}
      className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 rounded text-sm disabled:opacity-50"
    >
      {isPending ? 'Loading...' : 'Expand Connections'}
    </button>
  );
}
```

**Acceptance Criteria**:
- [ ] Expand button fetches connections
- [ ] New nodes appear in graph
- [ ] Edges connect correctly
- [ ] Existing entities not duplicated

---

## Phase 10: Detail Panel & Polish (Week 23-24)

### Task 10.1: Implement Full Detail Panel

Update `src/components/detail/DetailPanel.tsx`:

```typescript
import { useQuery } from '@tanstack/react-query';
import { useSelectionStore } from '@/stores/selectionStore';
import { getEntity } from '@/api/entities';
import { useGraphExpansion } from '@/hooks/useGraphExpansion';
import { RiskBadge } from '../common/RiskBadge';
import { EntityTypeBadge } from '../common/EntityTypeBadge';
import { X, ExternalLink, Plus, Flag } from 'lucide-react';

export function DetailPanel() {
  const { selectedIds, clearSelection } = useSelectionStore();
  const entityId = selectedIds[0];
  
  const { data: entity, isLoading, error } = useQuery({
    queryKey: ['entity', entityId],
    queryFn: () => getEntity(entityId),
    enabled: !!entityId,
  });
  
  const { mutate: expand, isPending: isExpanding } = useGraphExpansion();
  
  if (!entityId) {
    return (
      <div className="p-4 text-gray-400 text-center">
        <p>Select an entity to view details</p>
      </div>
    );
  }
  
  if (isLoading) {
    return (
      <div className="p-4 text-gray-400">
        <p>Loading...</p>
      </div>
    );
  }
  
  if (error || !entity) {
    return (
      <div className="p-4 text-red-400">
        <p>Error loading entity</p>
      </div>
    );
  }
  
  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="p-4 border-b border-gray-700">
        <div className="flex items-start justify-between">
          <div className="flex-1 min-w-0">
            <h2 className="text-lg font-semibold truncate">{entity.canonical_name}</h2>
            <div className="flex items-center gap-2 mt-1">
              <EntityTypeBadge type={entity.entity_type} />
              <RiskBadge score={entity.attributes?.risk_score as number} />
            </div>
          </div>
          <button
            onClick={clearSelection}
            className="p-1 hover:bg-gray-700 rounded"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>
      
      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Identifiers */}
        {entity.identifiers.length > 0 && (
          <Section title="Identifiers">
            {entity.identifiers.map((id, i) => (
              <div key={i} className="flex justify-between text-sm">
                <span className="text-gray-400">{id.identifier_type}</span>
                <span className="font-mono">{id.identifier_value}</span>
              </div>
            ))}
          </Section>
        )}
        
        {/* Type-specific attributes */}
        <Section title="Attributes">
          {entity.entity_type === 'PERSON' && (
            <PersonAttributes attrs={entity.attributes} />
          )}
          {entity.entity_type === 'COMPANY' && (
            <CompanyAttributes attrs={entity.attributes} />
          )}
          {entity.entity_type === 'ADDRESS' && (
            <AddressAttributes attrs={entity.attributes} />
          )}
        </Section>
        
        {/* Risk factors */}
        {entity.attributes?.risk_factors && (
          <Section title="Risk Factors">
            <div className="flex flex-wrap gap-1">
              {(entity.attributes.risk_factors as string[]).map((factor, i) => (
                <span
                  key={i}
                  className="px-2 py-0.5 bg-red-900/50 text-red-300 rounded text-xs"
                >
                  {factor}
                </span>
              ))}
            </div>
          </Section>
        )}
      </div>
      
      {/* Actions */}
      <div className="p-4 border-t border-gray-700 space-y-2">
        <button
          onClick={() => expand({ entityId, limit: 10 })}
          disabled={isExpanding}
          className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-blue-600 hover:bg-blue-500 rounded text-sm disabled:opacity-50"
        >
          <Plus className="w-4 h-4" />
          {isExpanding ? 'Loading...' : 'Expand Connections'}
        </button>
        <div className="flex gap-2">
          <button className="flex-1 flex items-center justify-center gap-2 px-3 py-2 bg-gray-700 hover:bg-gray-600 rounded text-sm">
            <Flag className="w-4 h-4" />
            Flag
          </button>
          <button className="flex-1 flex items-center justify-center gap-2 px-3 py-2 bg-gray-700 hover:bg-gray-600 rounded text-sm">
            <ExternalLink className="w-4 h-4" />
            Open
          </button>
        </div>
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="text-sm font-medium text-gray-400 mb-2">{title}</h3>
      <div className="space-y-1">{children}</div>
    </div>
  );
}

function PersonAttributes({ attrs }: { attrs: Record<string, unknown> }) {
  return (
    <>
      {attrs.birth_year && <AttrRow label="Birth Year" value={attrs.birth_year} />}
      {attrs.gender && <AttrRow label="Gender" value={attrs.gender === 'M' ? 'Male' : 'Female'} />}
      <AttrRow label="Companies" value={attrs.company_count ?? 0} />
    </>
  );
}

function CompanyAttributes({ attrs }: { attrs: Record<string, unknown> }) {
  return (
    <>
      {attrs.legal_form && <AttrRow label="Legal Form" value={attrs.legal_form} />}
      <AttrRow label="Status" value={attrs.status ?? 'Unknown'} />
      {attrs.registration_date && <AttrRow label="Registered" value={attrs.registration_date} />}
      {attrs.sni_primary && <AttrRow label="Industry (SNI)" value={attrs.sni_primary} />}
      {attrs.latest_employees !== undefined && <AttrRow label="Employees" value={attrs.latest_employees} />}
    </>
  );
}

function AddressAttributes({ attrs }: { attrs: Record<string, unknown> }) {
  return (
    <>
      <AttrRow label="Street" value={`${attrs.street} ${attrs.street_number ?? ''}`} />
      <AttrRow label="Postal Code" value={attrs.postal_code} />
      <AttrRow label="City" value={attrs.city} />
      {attrs.vulnerable_area && (
        <div className="mt-2 px-2 py-1 bg-red-900/50 text-red-300 rounded text-xs">
          Vulnerable Area
        </div>
      )}
    </>
  );
}

function AttrRow({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="flex justify-between text-sm">
      <span className="text-gray-400">{label}</span>
      <span>{String(value)}</span>
    </div>
  );
}
```

Create `src/components/common/RiskBadge.tsx`:

```typescript
import { riskColor } from '@/lib/colors';

export function RiskBadge({ score }: { score?: number }) {
  if (score === undefined || score === null) return null;
  
  const color = riskColor(score);
  const label = score < 0.3 ? 'Low' : score < 0.6 ? 'Medium' : score < 0.8 ? 'High' : 'Critical';
  
  return (
    <span
      className="px-2 py-0.5 rounded text-xs font-medium"
      style={{ backgroundColor: `${color}20`, color }}
    >
      {label} ({(score * 100).toFixed(0)}%)
    </span>
  );
}
```

Create `src/components/common/EntityTypeBadge.tsx`:

```typescript
import { entityTypeColor } from '@/lib/colors';

export function EntityTypeBadge({ type }: { type: string }) {
  const color = entityTypeColor(type);
  
  return (
    <span
      className="px-2 py-0.5 rounded text-xs font-medium"
      style={{ backgroundColor: `${color}20`, color }}
    >
      {type}
    </span>
  );
}
```

**Acceptance Criteria**:
- [ ] Detail panel shows all entity info
- [ ] Type-specific attributes displayed
- [ ] Risk factors shown as tags
- [ ] Expand button works
- [ ] Close button clears selection

### Task 10.2: Implement Filter Panel

Update `src/components/common/FilterPanel.tsx`:

```typescript
import { useFilterStore } from '@/stores/filterStore';
import { ChevronDown } from 'lucide-react';

export function FilterPanel() {
  const {
    entityTypes,
    setEntityTypes,
    predicates,
    setPredicates,
    riskRange,
    setRiskRange,
  } = useFilterStore();
  
  return (
    <div className="p-4 space-y-4">
      {/* Entity Types */}
      <FilterSection title="Entity Types">
        <Checkbox
          checked={entityTypes.includes('COMPANY')}
          onChange={() => toggleItem(entityTypes, 'COMPANY', setEntityTypes)}
          label="Companies"
          color="#8b5cf6"
        />
        <Checkbox
          checked={entityTypes.includes('PERSON')}
          onChange={() => toggleItem(entityTypes, 'PERSON', setEntityTypes)}
          label="Persons"
          color="#3b82f6"
        />
        <Checkbox
          checked={entityTypes.includes('ADDRESS')}
          onChange={() => toggleItem(entityTypes, 'ADDRESS', setEntityTypes)}
          label="Addresses"
          color="#06b6d4"
        />
      </FilterSection>
      
      {/* Relationships */}
      <FilterSection title="Relationships">
        <Checkbox
          checked={predicates.includes('DIRECTOR_OF')}
          onChange={() => toggleItem(predicates, 'DIRECTOR_OF', setPredicates)}
          label="Directors"
        />
        <Checkbox
          checked={predicates.includes('SHAREHOLDER_OF')}
          onChange={() => toggleItem(predicates, 'SHAREHOLDER_OF', setPredicates)}
          label="Shareholders"
        />
        <Checkbox
          checked={predicates.includes('REGISTERED_AT')}
          onChange={() => toggleItem(predicates, 'REGISTERED_AT', setPredicates)}
          label="Addresses"
        />
      </FilterSection>
      
      {/* Risk Range */}
      <FilterSection title="Risk Score">
        <div className="px-1">
          <input
            type="range"
            min={0}
            max={100}
            value={riskRange[0] * 100}
            onChange={(e) => setRiskRange([parseInt(e.target.value) / 100, riskRange[1]])}
            className="w-full"
          />
          <div className="flex justify-between text-xs text-gray-400 mt-1">
            <span>{(riskRange[0] * 100).toFixed(0)}%</span>
            <span>{(riskRange[1] * 100).toFixed(0)}%</span>
          </div>
        </div>
      </FilterSection>
    </div>
  );
}

function FilterSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h4 className="text-sm font-medium text-gray-400 mb-2 flex items-center gap-1">
        {title}
        <ChevronDown className="w-3 h-3" />
      </h4>
      <div className="space-y-1">{children}</div>
    </div>
  );
}

function Checkbox({
  checked,
  onChange,
  label,
  color,
}: {
  checked: boolean;
  onChange: () => void;
  label: string;
  color?: string;
}) {
  return (
    <label className="flex items-center gap-2 cursor-pointer hover:bg-gray-800 px-2 py-1 rounded">
      <input
        type="checkbox"
        checked={checked}
        onChange={onChange}
        className="rounded border-gray-600"
      />
      {color && (
        <span
          className="w-2 h-2 rounded-full"
          style={{ backgroundColor: color }}
        />
      )}
      <span className="text-sm">{label}</span>
    </label>
  );
}

function toggleItem<T>(arr: T[], item: T, setter: (arr: T[]) => void) {
  if (arr.includes(item)) {
    setter(arr.filter((i) => i !== item));
  } else {
    setter([...arr, item]);
  }
}
```

**Acceptance Criteria**:
- [ ] Entity type filters work
- [ ] Relationship filters work
- [ ] Risk slider updates filter
- [ ] Map/graph responds to filter changes

---

## Final Checklist

### Backend
- [ ] All models and migrations complete
- [ ] Entity resolution pipeline working
- [ ] Shell network detection working
- [ ] Spatial aggregation endpoints implemented
- [ ] All API endpoints returning correct data
- [ ] Performance targets met

### Frontend
- [ ] Discovery map with semantic zoom
- [ ] Cluster layer at low zoom
- [ ] Entity layer at high zoom
- [ ] Investigation workspace with Cytoscape
- [ ] Progressive expansion working
- [ ] Detail panel complete
- [ ] Filter panel complete
- [ ] Mode switching works
- [ ] Selection sync between views

### Integration
- [ ] Frontend connects to backend API
- [ ] Data flows correctly end-to-end
- [ ] No console errors
- [ ] Responsive at target data volumes

---

*Execute each task in order. Do not skip tasks. Verify acceptance criteria before proceeding.*