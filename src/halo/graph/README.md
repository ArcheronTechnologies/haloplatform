# Halo Intelligence Graph

The graph module provides a flexible graph-based data model for representing entities, relationships, and networks in the Swedish business ecosystem.

## Architecture

```
graph/
├── __init__.py      # Module exports
├── schema.py        # Node type definitions (Person, Company, Address, etc.)
├── edges.py         # Edge type definitions (ownership, directorships, etc.)
├── client.py        # Graph client with NetworkX and Neo4j backends
└── README.md        # This file
```

## Node Types

### Person
Represents an individual (director, beneficial owner, signatory).

```python
from halo.graph.schema import Person

person = Person(
    personnummer="PROTECTED",
    names=[{"first": "Johan", "last": "Svensson"}],
    nationality="SE",
    pep_status={"is_pep": False, "category": None},
    sanctions_hits=[],
    risk_score=0.0
)

# Properties
print(person.display_name)    # "Johan Svensson"
print(person.is_pep)          # False
print(person.has_sanctions_hit)  # False
```

### Company
Represents a Swedish company (AB, HB, etc.).

```python
from halo.graph.schema import Company

company = Company(
    orgnr="5560001234",
    names=[{"name": "Test AB", "from_date": "2020-01-01"}],
    legal_form="AB",
    status={"code": "active", "text": "Aktiv"},
    formation={"date": "2020-01-01"},
    employees={"count": 10},
    f_skatt={"registered": True},
    vat={"registered": True},
    sni_codes=[{"code": "62010", "description": "Software development"}],
    shell_score=0.0,
    risk_score=0.0
)

# Properties
print(company.display_name)  # "Test AB"
print(company.is_active)     # True
print(company.has_f_skatt)   # True
print(company.has_vat)       # True
```

### Address
Represents a registered business address.

```python
from halo.graph.schema import Address

address = Address(
    street="Kungsgatan 1",
    postal_code="111 43",
    city="Stockholm",
    country="SE",
    type="commercial",
    is_virtual=False
)
```

### Other Node Types
- **Property**: Real estate assets
- **BankAccount**: Financial accounts (with encryption)
- **Document**: Årsredovisning, contracts, etc.

## Edge Types

### Ownership Edges

```python
from halo.graph.edges import OwnsEdge, BeneficialOwnerEdge

# Direct ownership
ownership = OwnsEdge(
    from_id="company-parent",
    from_type="company",
    to_id="company-child",
    ownership_pct=100.0,
    from_date="2020-01-01"
)

# Beneficial ownership
beneficial = BeneficialOwnerEdge(
    from_id="person-1",
    to_id="company-1",
    ownership_pct=51.0,
    control_type="shares"
)
```

### Directorship Edges

```python
from halo.graph.edges import DirectsEdge, SignatoryEdge

directorship = DirectsEdge(
    from_id="person-1",
    to_id="company-1",
    role="styrelseledamot",  # Board member
    from_date="2020-01-01"
)

signatory = SignatoryEdge(
    from_id="person-1",
    to_id="company-1",
    type="firmatecknare"  # Signatory
)
```

### Location Edges

```python
from halo.graph.edges import RegisteredAtEdge

registration = RegisteredAtEdge(
    from_id="company-1",
    to_id="address-1",
    type="registered",  # or "visiting"
    from_date="2020-01-01"
)
```

## Graph Client

The GraphClient provides a unified interface for graph operations with pluggable backends.

### NetworkX Backend (Default)

```python
from halo.graph.client import GraphClient
from halo.graph.schema import Company, Person
from halo.graph.edges import DirectsEdge

# Create client
client = GraphClient()  # Uses NetworkX by default

async with client:
    # Add nodes
    company = Company(id="company-1", orgnr="5560001234")
    await client.add_company(company)

    person = Person(id="person-1")
    await client.add_person(person)

    # Add edges
    await client.add_directorship(DirectsEdge(
        from_id="person-1",
        to_id="company-1",
        role="styrelseledamot"
    ))

    # Query
    entity = await client.get_entity("company-1")
    neighbors = await client.get_neighbors("company-1", hops=2)
```

### Neo4j Backend

```python
from halo.graph.client import GraphClient

client = GraphClient(
    backend="neo4j",
    uri="bolt://localhost:7687",
    user="neo4j",
    password="password"
)

async with client:
    # Same API as NetworkX
    results = await client.query("""
        MATCH (c:Company)-[:REGISTERED_AT]->(a:Address)
        WHERE a.city = 'Stockholm'
        RETURN c
    """)
```

### Network Analysis

```python
# Compute centrality metrics
metrics = client.compute_centrality()
# Returns: {
#   "degree": {"node-1": 0.5, ...},
#   "betweenness": {"node-1": 0.3, ...},
#   "pagerank": {"node-1": 0.02, ...},
#   "clustering": {"node-1": 0.4, ...}
# }

# Find connected components
components = client.find_connected_components()
# Returns list of node ID sets

# Get entity with full context
entity = await client.get_entity_with_context("company-1")
# Returns entity data + network metrics + risk scores
```

## Swedish Business Concepts

### Organisation Number (Organisationsnummer)
- 10-digit identifier for Swedish companies
- Format: NNNNNNNNNN (e.g., 5560001234)
- First digit indicates entity type (5 = AB, 9 = Sole proprietor, etc.)

### F-skatt
- Tax registration for performing work/services
- Companies need this to invoice for services
- Shell companies often have F-skatt but no real operations

### SNI Codes
- Swedish industry classification (similar to NACE)
- Indicates business activity
- Generic codes (70100 = Holding, 82110 = Office support) are risk indicators

### Legal Forms
- **AB**: Aktiebolag (Limited company) - 50,000 SEK minimum capital
- **HB**: Handelsbolag (Trading partnership)
- **KB**: Kommanditbolag (Limited partnership)
- **EF**: Enskild firma (Sole proprietorship)

## Testing

```bash
# Run graph module tests
python -m pytest halo/tests/test_graph_*.py -v
```

## Best Practices

1. **Use async context manager**: Always use `async with client:` to ensure proper connection management
2. **Add nodes before edges**: Ensure nodes exist before creating edges between them
3. **Use meaningful IDs**: Consider using UUID or composite keys for entity IDs
4. **Normalize identifiers**: Strip dashes/spaces from organisationsnummer and personnummer
5. **Handle None values**: Check for None before accessing nested dict properties
