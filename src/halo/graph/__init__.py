"""
Halo Intelligence Graph Module.

Graph-based intelligence platform for mapping networks of criminality/fraud
across persons, businesses, addresses, and accounts.

Tech Stack:
- Storage: PostgreSQL + Apache AGE (graph extension) or Neo4j
- Processing: NetworkX (Python) for graph algorithms
- Visualization: D3.js force-directed, Cytoscape.js, or vis.js
"""

from halo.graph.schema import (
    Person,
    Company,
    Address,
    Property,
    BankAccount,
    Document,
)
from halo.graph.edges import (
    DirectsEdge,
    OwnsEdge,
    BeneficialOwnerEdge,
    RegisteredAtEdge,
    LivesAtEdge,
    CoDirectorEdge,
    CoRegisteredEdge,
    TransactsEdge,
    SameAsEdge,
)
from halo.graph.client import GraphClient, create_graph_client, Neo4jBackend, NetworkXBackend
from halo.graph.age_backend import AgeBackend, create_age_backend

__all__ = [
    # Nodes
    "Person",
    "Company",
    "Address",
    "Property",
    "BankAccount",
    "Document",
    # Edges
    "DirectsEdge",
    "OwnsEdge",
    "BeneficialOwnerEdge",
    "RegisteredAtEdge",
    "LivesAtEdge",
    "CoDirectorEdge",
    "CoRegisteredEdge",
    "TransactsEdge",
    "SameAsEdge",
    # Client and Backends
    "GraphClient",
    "create_graph_client",
    "Neo4jBackend",
    "NetworkXBackend",
    "AgeBackend",
    "create_age_backend",
]
