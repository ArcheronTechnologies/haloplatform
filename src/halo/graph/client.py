"""
Graph Client for Halo Intelligence Platform.

Provides a unified interface for graph operations, supporting both
PostgreSQL with Apache AGE and Neo4j backends.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import asdict
from datetime import datetime
from typing import Any, Optional, TypeVar, Union

import networkx as nx

from halo.graph.schema import Person, Company, Address, Property, BankAccount, Document
from halo.graph.edges import (
    DirectsEdge, OwnsEdge, BeneficialOwnerEdge, RegisteredAtEdge,
    LivesAtEdge, CoDirectorEdge, CoRegisteredEdge, TransactsEdge, SameAsEdge
)

logger = logging.getLogger(__name__)

NodeType = Union[Person, Company, Address, Property, BankAccount, Document]
EdgeType = Union[
    DirectsEdge, OwnsEdge, BeneficialOwnerEdge, RegisteredAtEdge,
    LivesAtEdge, CoDirectorEdge, CoRegisteredEdge, TransactsEdge, SameAsEdge
]
T = TypeVar("T")


class GraphBackend(ABC):
    """Abstract base class for graph database backends."""

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to the graph database."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close the database connection."""
        pass

    @abstractmethod
    async def execute(self, query: str, params: Optional[dict] = None) -> list[dict]:
        """Execute a graph query and return results."""
        pass

    @abstractmethod
    async def create_node(self, node: NodeType) -> str:
        """Create a node and return its ID."""
        pass

    @abstractmethod
    async def create_edge(self, edge: EdgeType) -> str:
        """Create an edge and return its ID."""
        pass

    @abstractmethod
    async def get_node(self, node_id: str, node_type: str) -> Optional[dict]:
        """Get a node by ID."""
        pass

    @abstractmethod
    async def get_neighbors(
        self,
        node_id: str,
        edge_types: Optional[list[str]] = None,
        direction: str = "both"
    ) -> list[dict]:
        """Get neighboring nodes."""
        pass


class Neo4jBackend(GraphBackend):
    """
    Neo4j graph database backend for production use.

    Features:
    - Connection pooling
    - Automatic index/constraint creation
    - Transaction support
    - Full Cypher query execution
    """

    # Schema setup queries
    SCHEMA_QUERIES = [
        # Constraints (unique IDs)
        "CREATE CONSTRAINT person_id IF NOT EXISTS FOR (n:Person) REQUIRE n.id IS UNIQUE",
        "CREATE CONSTRAINT company_id IF NOT EXISTS FOR (n:Company) REQUIRE n.id IS UNIQUE",
        "CREATE CONSTRAINT address_id IF NOT EXISTS FOR (n:Address) REQUIRE n.id IS UNIQUE",
        "CREATE CONSTRAINT property_id IF NOT EXISTS FOR (n:Property) REQUIRE n.id IS UNIQUE",
        "CREATE CONSTRAINT bank_account_id IF NOT EXISTS FOR (n:BankAccount) REQUIRE n.id IS UNIQUE",
        "CREATE CONSTRAINT document_id IF NOT EXISTS FOR (n:Document) REQUIRE n.id IS UNIQUE",
        # Indexes for common lookups
        "CREATE INDEX company_orgnr IF NOT EXISTS FOR (n:Company) ON (n.orgnr)",
        "CREATE INDEX person_personnummer IF NOT EXISTS FOR (n:Person) ON (n.personnummer)",
        "CREATE INDEX company_status IF NOT EXISTS FOR (n:Company) ON (n.status)",
        "CREATE INDEX company_risk_score IF NOT EXISTS FOR (n:Company) ON (n.risk_score)",
        "CREATE INDEX company_shell_score IF NOT EXISTS FOR (n:Company) ON (n.shell_score)",
        "CREATE INDEX person_risk_score IF NOT EXISTS FOR (n:Person) ON (n.risk_score)",
        "CREATE INDEX address_city IF NOT EXISTS FOR (n:Address) ON (n.city)",
    ]

    def __init__(
        self,
        uri: str,
        user: str,
        password: str,
        database: str = "neo4j",
        max_connection_pool_size: int = 50,
        connection_timeout: float = 30.0,
        auto_setup_schema: bool = True,
    ):
        self.uri = uri
        self.user = user
        self.password = password
        self.database = database
        self.max_connection_pool_size = max_connection_pool_size
        self.connection_timeout = connection_timeout
        self.auto_setup_schema = auto_setup_schema
        self._driver = None
        self._schema_initialized = False

    async def connect(self) -> None:
        """Connect to Neo4j with connection pooling."""
        try:
            from neo4j import AsyncGraphDatabase
            self._driver = AsyncGraphDatabase.driver(
                self.uri,
                auth=(self.user, self.password),
                max_connection_pool_size=self.max_connection_pool_size,
                connection_timeout=self.connection_timeout,
            )
            # Verify connectivity
            await self._driver.verify_connectivity()
            logger.info(f"Connected to Neo4j at {self.uri}")

            # Setup schema
            if self.auto_setup_schema and not self._schema_initialized:
                await self._setup_schema()

        except ImportError:
            raise ImportError("neo4j package required. Install with: pip install neo4j")
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
            raise

    async def _setup_schema(self) -> None:
        """Create indexes and constraints."""
        logger.info("Setting up Neo4j schema...")
        for query in self.SCHEMA_QUERIES:
            try:
                await self.execute(query)
            except Exception as e:
                # Log but don't fail - constraint may already exist
                logger.debug(f"Schema query skipped: {e}")
        self._schema_initialized = True
        logger.info("Neo4j schema setup complete")

    async def close(self) -> None:
        """Close Neo4j connection."""
        if self._driver:
            await self._driver.close()
            self._driver = None
            logger.info("Neo4j connection closed")

    async def execute(self, query: str, params: Optional[dict] = None) -> list[dict]:
        """Execute a Cypher query."""
        if not self._driver:
            raise RuntimeError("Not connected to Neo4j")

        async with self._driver.session(database=self.database) as session:
            result = await session.run(query, params or {})
            records = await result.data()
            return records

    async def execute_write(self, query: str, params: Optional[dict] = None) -> list[dict]:
        """Execute a write transaction."""
        if not self._driver:
            raise RuntimeError("Not connected to Neo4j")

        async def _tx_func(tx):
            result = await tx.run(query, params or {})
            return await result.data()

        async with self._driver.session(database=self.database) as session:
            return await session.execute_write(_tx_func)

    async def execute_batch(self, queries: list[tuple[str, dict]]) -> list[list[dict]]:
        """Execute multiple queries in a single transaction."""
        if not self._driver:
            raise RuntimeError("Not connected to Neo4j")

        async def _tx_func(tx):
            results = []
            for query, params in queries:
                result = await tx.run(query, params)
                results.append(await result.data())
            return results

        async with self._driver.session(database=self.database) as session:
            return await session.execute_write(_tx_func)

    async def create_node(self, node: NodeType) -> str:
        """Create a node in Neo4j."""
        import json
        node_type = type(node).__name__
        data = asdict(node)

        # Convert complex types to JSON strings for storage
        for key, value in list(data.items()):
            if isinstance(value, (list, dict)):
                data[key] = json.dumps(value)
            elif isinstance(value, datetime):
                data[key] = value.isoformat()
            elif value is None:
                del data[key]  # Neo4j doesn't like None values

        # Use MERGE to avoid duplicates
        query = f"""
        MERGE (n:{node_type} {{id: $id}})
        SET n += $props
        RETURN n.id as id
        """
        result = await self.execute_write(query, {"id": node.id, "props": data})
        return result[0]["id"] if result else node.id

    async def create_edge(self, edge: EdgeType) -> str:
        """Create an edge in Neo4j."""
        import json
        edge_type = type(edge).__name__.replace("Edge", "").upper()
        data = asdict(edge)

        from_id = data.pop("from_id")
        to_id = data.pop("to_id")
        from_type = data.pop("from_type", None)

        # Convert complex types
        for key, value in list(data.items()):
            if isinstance(value, (list, dict)):
                data[key] = json.dumps(value)
            elif isinstance(value, datetime):
                data[key] = value.isoformat()
            elif value is None:
                del data[key]

        # MERGE to avoid duplicate edges
        query = f"""
        MATCH (a {{id: $from_id}})
        MATCH (b {{id: $to_id}})
        MERGE (a)-[r:{edge_type}]->(b)
        SET r += $props
        RETURN r.id as id
        """
        result = await self.execute_write(query, {
            "from_id": from_id,
            "to_id": to_id,
            "props": data
        })
        return result[0]["id"] if result else edge.id

    async def create_nodes_batch(self, nodes: list[NodeType]) -> list[str]:
        """Create multiple nodes in a single transaction."""
        import json
        if not nodes:
            return []

        queries = []
        for node in nodes:
            node_type = type(node).__name__
            data = asdict(node)
            for key, value in list(data.items()):
                if isinstance(value, (list, dict)):
                    data[key] = json.dumps(value)
                elif isinstance(value, datetime):
                    data[key] = value.isoformat()
                elif value is None:
                    del data[key]

            query = f"""
            MERGE (n:{node_type} {{id: $id}})
            SET n += $props
            RETURN n.id as id
            """
            queries.append((query, {"id": node.id, "props": data}))

        results = await self.execute_batch(queries)
        return [r[0]["id"] if r else nodes[i].id for i, r in enumerate(results)]

    async def get_node(self, node_id: str, node_type: str) -> Optional[dict]:
        """Get a node by ID."""
        import json
        query = f"""
        MATCH (n:{node_type} {{id: $id}})
        RETURN n, labels(n) as labels
        """
        result = await self.execute(query, {"id": node_id})
        if not result:
            return None

        node = dict(result[0]["n"])
        node["_type"] = node_type

        # Parse JSON fields
        for key, value in node.items():
            if isinstance(value, str) and value.startswith(('[', '{')):
                try:
                    node[key] = json.loads(value)
                except json.JSONDecodeError:
                    pass

        return node

    async def get_neighbors(
        self,
        node_id: str,
        edge_types: Optional[list[str]] = None,
        direction: str = "both"
    ) -> list[dict]:
        """Get neighboring nodes."""
        import json
        edge_filter = ""
        if edge_types:
            # Convert edge type names to relationship types
            rel_types = [t.replace("Edge", "").upper() for t in edge_types]
            edge_filter = ":" + "|".join(rel_types)

        if direction == "out":
            pattern = f"(n)-[r{edge_filter}]->(m)"
        elif direction == "in":
            pattern = f"(n)<-[r{edge_filter}]-(m)"
        else:
            pattern = f"(n)-[r{edge_filter}]-(m)"

        query = f"""
        MATCH {pattern}
        WHERE n.id = $id
        RETURN m, type(r) as edge_type, properties(r) as edge, labels(m) as labels
        """
        results = await self.execute(query, {"id": node_id})

        neighbors = []
        for row in results:
            node = dict(row["m"])
            node["_type"] = row["labels"][0] if row["labels"] else "Unknown"

            # Parse JSON fields
            for key, value in node.items():
                if isinstance(value, str) and value.startswith(('[', '{')):
                    try:
                        node[key] = json.loads(value)
                    except json.JSONDecodeError:
                        pass

            edge = dict(row["edge"]) if row["edge"] else {}
            edge["_type"] = row["edge_type"]

            neighbors.append({
                "m": node,
                "edge_type": row["edge_type"],
                "edge": edge
            })

        return neighbors

    async def find_by_orgnr(self, orgnr: str) -> Optional[dict]:
        """Find a company by organisationsnummer."""
        query = """
        MATCH (c:Company {orgnr: $orgnr})
        RETURN c
        """
        result = await self.execute(query, {"orgnr": orgnr})
        return dict(result[0]["c"]) if result else None

    async def find_by_personnummer(self, personnummer: str) -> Optional[dict]:
        """Find a person by personnummer."""
        query = """
        MATCH (p:Person {personnummer: $personnummer})
        RETURN p
        """
        result = await self.execute(query, {"personnummer": personnummer})
        return dict(result[0]["p"]) if result else None

    async def get_companies_at_address(self, address_id: str) -> list[dict]:
        """Get all companies registered at an address."""
        query = """
        MATCH (c:Company)-[:REGISTEREDAT]->(a:Address {id: $address_id})
        RETURN c
        """
        results = await self.execute(query, {"address_id": address_id})
        return [dict(r["c"]) for r in results]

    async def get_directorships(self, person_id: str) -> list[dict]:
        """Get all companies a person directs."""
        query = """
        MATCH (p:Person {id: $person_id})-[r:DIRECTS]->(c:Company)
        RETURN c, r.role as role
        """
        results = await self.execute(query, {"person_id": person_id})
        return [{"company": dict(r["c"]), "role": r["role"]} for r in results]

    async def get_ownership_chain(self, company_id: str, max_depth: int = 10) -> list[dict]:
        """Traverse ownership chain to find beneficial owners."""
        query = """
        MATCH path = (start:Company {id: $company_id})<-[:OWNS*1..$max_depth]-(owner)
        RETURN owner, length(path) as depth,
               [r in relationships(path) | r.ownership_pct] as shares
        """
        results = await self.execute(query, {"company_id": company_id, "max_depth": max_depth})
        return [
            {
                "owner": dict(r["owner"]),
                "depth": r["depth"],
                "shares": r["shares"]
            }
            for r in results
        ]

    async def find_circular_ownership(self, max_length: int = 6) -> list[list[str]]:
        """Find circular ownership patterns."""
        query = """
        MATCH path = (c:Company)-[:OWNS*2..$max_length]->(c)
        RETURN [n in nodes(path) | n.id] as cycle
        LIMIT 100
        """
        results = await self.execute(query, {"max_length": max_length})
        return [r["cycle"] for r in results]

    async def get_network_statistics(self) -> dict:
        """Get overall graph statistics."""
        query = """
        MATCH (n)
        WITH labels(n) as types, count(*) as count
        RETURN types[0] as type, count
        UNION ALL
        MATCH ()-[r]->()
        WITH type(r) as rel_type, count(*) as count
        RETURN rel_type as type, count
        """
        results = await self.execute(query)
        return {r["type"]: r["count"] for r in results}


class NetworkXBackend(GraphBackend):
    """
    In-memory NetworkX backend for development/testing.

    Also useful for graph algorithm computations.
    """

    def __init__(self):
        self.graph = nx.MultiDiGraph()
        self._nodes: dict[str, dict] = {}
        self._edges: dict[str, dict] = {}

    async def connect(self) -> None:
        """Initialize the graph."""
        logger.info("Initialized NetworkX in-memory graph")

    async def close(self) -> None:
        """Clear the graph."""
        self.graph.clear()
        self._nodes.clear()
        self._edges.clear()

    async def execute(self, query: str, params: Optional[dict] = None) -> list[dict]:
        """
        Execute a query.

        Note: NetworkX doesn't support Cypher - this is for simple pattern matching.
        For complex queries, use the Neo4j backend.
        """
        raise NotImplementedError(
            "NetworkX backend doesn't support Cypher queries. "
            "Use Neo4j for pattern matching."
        )

    async def create_node(self, node: NodeType) -> str:
        """Create a node in the graph."""
        node_type = type(node).__name__
        data = asdict(node)
        data["_type"] = node_type

        self.graph.add_node(node.id, **data)
        self._nodes[node.id] = data

        return node.id

    async def create_edge(self, edge: EdgeType) -> str:
        """Create an edge in the graph."""
        edge_type = type(edge).__name__
        data = asdict(edge)
        data["_type"] = edge_type

        from_id = data["from_id"]
        to_id = data["to_id"]

        self.graph.add_edge(from_id, to_id, key=edge.id, **data)
        self._edges[edge.id] = data

        return edge.id

    async def get_node(self, node_id: str, node_type: str) -> Optional[dict]:
        """Get a node by ID."""
        if node_id in self._nodes:
            node = self._nodes[node_id]
            if node.get("_type") == node_type:
                return node
        return None

    async def get_neighbors(
        self,
        node_id: str,
        edge_types: Optional[list[str]] = None,
        direction: str = "both"
    ) -> list[dict]:
        """Get neighboring nodes."""
        neighbors = []

        if direction in ("out", "both"):
            for _, target, data in self.graph.out_edges(node_id, data=True):
                if edge_types is None or data.get("_type") in edge_types:
                    neighbors.append({
                        "m": self._nodes.get(target, {}),
                        "edge_type": data.get("_type"),
                        "edge": data
                    })

        if direction in ("in", "both"):
            for source, _, data in self.graph.in_edges(node_id, data=True):
                if edge_types is None or data.get("_type") in edge_types:
                    neighbors.append({
                        "m": self._nodes.get(source, {}),
                        "edge_type": data.get("_type"),
                        "edge": data
                    })

        return neighbors

    # NetworkX-specific graph algorithms

    def compute_centrality(self) -> dict[str, dict[str, float]]:
        """Compute various centrality metrics for all nodes."""
        # Convert to simple graph for clustering (multigraph not supported)
        simple_undirected = nx.Graph(self.graph.to_undirected())

        result = {
            "degree": dict(nx.degree_centrality(self.graph)),
            "betweenness": dict(nx.betweenness_centrality(self.graph)),
            "pagerank": {},
            "clustering": {},
        }

        # PageRank needs at least one edge
        if self.graph.number_of_edges() > 0:
            try:
                result["pagerank"] = dict(nx.pagerank(self.graph))
            except nx.PowerIterationFailedConvergence:
                result["pagerank"] = {n: 0.0 for n in self.graph.nodes()}
        else:
            result["pagerank"] = {n: 0.0 for n in self.graph.nodes()}

        # Clustering needs simple undirected graph
        if simple_undirected.number_of_nodes() > 0:
            result["clustering"] = dict(nx.clustering(simple_undirected))

        return result

    def find_communities(self) -> list[set[str]]:
        """Find communities using Louvain algorithm."""
        try:
            from networkx.algorithms.community import louvain_communities
            undirected = self.graph.to_undirected()
            return louvain_communities(undirected)
        except ImportError:
            logger.warning("Community detection requires python-louvain package")
            return []

    def shortest_path(self, source: str, target: str) -> Optional[list[str]]:
        """Find shortest path between two nodes."""
        try:
            return nx.shortest_path(self.graph, source, target)
        except nx.NetworkXNoPath:
            return None

    def find_cycles(self, max_length: int = 6) -> list[list[str]]:
        """Find cycles in the graph (for circular ownership detection)."""
        cycles = []
        try:
            for cycle in nx.simple_cycles(self.graph):
                if len(cycle) <= max_length:
                    cycles.append(cycle)
        except nx.NetworkXError:
            pass
        return cycles


class GraphClient:
    """
    High-level graph client for the Halo intelligence platform.

    Provides a unified interface regardless of backend.
    """

    def __init__(self, backend: Optional[GraphBackend] = None):
        """
        Initialize the graph client.

        Args:
            backend: Graph backend to use. Defaults to NetworkX for development.
        """
        self.backend = backend or NetworkXBackend()
        self._connected = False

    async def connect(self) -> None:
        """Connect to the graph database."""
        await self.backend.connect()
        self._connected = True

    async def close(self) -> None:
        """Close the connection."""
        await self.backend.close()
        self._connected = False

    async def __aenter__(self) -> "GraphClient":
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    # Node operations

    async def add_person(self, person: Person) -> str:
        """Add a person to the graph."""
        return await self.backend.create_node(person)

    async def add_company(self, company: Company) -> str:
        """Add a company to the graph."""
        return await self.backend.create_node(company)

    async def add_address(self, address: Address) -> str:
        """Add an address to the graph."""
        return await self.backend.create_node(address)

    async def get_person(self, person_id: str) -> Optional[dict]:
        """Get a person by ID."""
        return await self.backend.get_node(person_id, "Person")

    async def get_company(self, company_id: str) -> Optional[dict]:
        """Get a company by ID."""
        return await self.backend.get_node(company_id, "Company")

    async def get_address(self, address_id: str) -> Optional[dict]:
        """Get an address by ID."""
        return await self.backend.get_node(address_id, "Address")

    # Edge operations

    async def add_directorship(self, edge: DirectsEdge) -> str:
        """Add a directorship relationship."""
        return await self.backend.create_edge(edge)

    async def add_ownership(self, edge: OwnsEdge) -> str:
        """Add an ownership relationship."""
        return await self.backend.create_edge(edge)

    async def add_registration(self, edge: RegisteredAtEdge) -> str:
        """Add a company-address registration."""
        return await self.backend.create_edge(edge)

    # Network operations

    async def expand_network(
        self,
        seed_entities: list[str],
        hops: int = 2,
        edge_types: Optional[list[str]] = None
    ) -> dict[str, Any]:
        """
        Expand network from seed entities.

        Returns nodes and edges within N hops.
        """
        visited = set()
        nodes = {}
        edges = []
        frontier = set(seed_entities)

        for _ in range(hops):
            next_frontier = set()

            for node_id in frontier:
                if node_id in visited:
                    continue

                visited.add(node_id)
                neighbors = await self.backend.get_neighbors(
                    node_id,
                    edge_types=edge_types
                )

                for neighbor in neighbors:
                    neighbor_node = neighbor.get("m", {})
                    neighbor_id = neighbor_node.get("id")

                    if neighbor_id:
                        nodes[neighbor_id] = neighbor_node
                        edges.append({
                            "from": node_id,
                            "to": neighbor_id,
                            "type": neighbor.get("edge_type"),
                            "data": neighbor.get("edge", {})
                        })

                        if neighbor_id not in visited:
                            next_frontier.add(neighbor_id)

            frontier = next_frontier

        return {
            "nodes": nodes,
            "edges": edges,
            "seed_entities": seed_entities,
            "hops": hops
        }

    async def get_companies_at_address(self, address_id: str) -> list[dict]:
        """Get all companies registered at an address."""
        neighbors = await self.backend.get_neighbors(
            address_id,
            edge_types=["RegisteredAtEdge"],
            direction="in"
        )
        return [n["m"] for n in neighbors if n["m"].get("_type") == "Company"]

    async def get_directorships(self, person_id: str) -> list[dict]:
        """Get all companies a person directs."""
        neighbors = await self.backend.get_neighbors(
            person_id,
            edge_types=["DirectsEdge"],
            direction="out"
        )
        return [
            {"company": n["m"], "role": n["edge"].get("role")}
            for n in neighbors
            if n["m"].get("_type") == "Company"
        ]

    async def get_ownership_chain(
        self,
        company_id: str,
        max_depth: int = 10
    ) -> list[dict]:
        """
        Traverse ownership chain upward to find beneficial owners.

        Returns the ownership path from company to ultimate owners.
        """
        chain = []
        visited = set()
        current = [company_id]

        for depth in range(max_depth):
            next_level = []

            for entity_id in current:
                if entity_id in visited:
                    continue

                visited.add(entity_id)
                neighbors = await self.backend.get_neighbors(
                    entity_id,
                    edge_types=["OwnsEdge"],
                    direction="in"
                )

                for neighbor in neighbors:
                    owner = neighbor["m"]
                    edge = neighbor["edge"]

                    chain.append({
                        "depth": depth,
                        "owner_id": owner.get("id"),
                        "owner_type": owner.get("_type"),
                        "owned_id": entity_id,
                        "share": edge.get("share", 0),
                    })

                    if owner.get("_type") == "Company":
                        next_level.append(owner.get("id"))

            if not next_level:
                break

            current = next_level

        return chain

    # Query execution

    async def query(self, query: str, params: Optional[dict] = None) -> list[dict]:
        """
        Execute a Cypher query.

        Works with Neo4j backend. NetworkX will raise NotImplementedError.
        """
        return await self.backend.execute(query, params)

    async def execute_cypher(self, query: str, params: Optional[dict] = None) -> list[dict]:
        """
        Execute a Cypher query.

        Alias for query() - works with Neo4j backend.
        """
        return await self.backend.execute(query, params)

    # Entity retrieval methods

    async def get_entity(self, entity_id: str) -> Optional[dict]:
        """Get any entity by ID (tries all node types)."""
        for node_type in ["Company", "Person", "Address", "Property", "BankAccount", "Document"]:
            result = await self.backend.get_node(entity_id, node_type)
            if result:
                return result
        return None

    async def get_entity_with_context(self, entity_id: str) -> Optional[dict]:
        """Get entity with network context and metrics."""
        entity = await self.get_entity(entity_id)
        if not entity:
            return None

        # Get neighbors
        neighbors = await self.get_neighbors(entity_id, hops=1)

        # Add context
        entity["neighbor_count"] = len(neighbors)
        entity["neighbors"] = neighbors[:10]  # First 10 neighbors

        # Add network metrics if available
        if isinstance(self.backend, NetworkXBackend):
            metrics = self.backend.compute_centrality()
            entity["network_metrics"] = {
                "degree": metrics.get("degree", {}).get(entity_id, 0),
                "betweenness": metrics.get("betweenness", {}).get(entity_id, 0),
                "pagerank": metrics.get("pagerank", {}).get(entity_id, 0),
                "clustering": metrics.get("clustering", {}).get(entity_id, 0),
            }

        return entity

    async def get_neighbors(
        self,
        entity_id: str,
        hops: int = 1,
        edge_types: Optional[list[str]] = None
    ) -> list[dict]:
        """Get neighbors of an entity up to N hops away."""
        if hops == 1:
            return await self.backend.get_neighbors(entity_id, edge_types=edge_types)

        # Multi-hop traversal
        visited = {entity_id}
        all_neighbors = []
        frontier = [entity_id]

        for _ in range(hops):
            next_frontier = []
            for node_id in frontier:
                neighbors = await self.backend.get_neighbors(node_id, edge_types=edge_types)
                for neighbor in neighbors:
                    neighbor_id = neighbor.get("m", {}).get("id")
                    if neighbor_id and neighbor_id not in visited:
                        visited.add(neighbor_id)
                        all_neighbors.append(neighbor)
                        next_frontier.append(neighbor_id)
            frontier = next_frontier

        return all_neighbors

    # Lookup methods

    async def find_company_by_orgnr(self, orgnr: str) -> Optional[dict]:
        """Find a company by organisationsnummer."""
        if isinstance(self.backend, Neo4jBackend):
            return await self.backend.find_by_orgnr(orgnr)
        # NetworkX fallback - search all nodes
        for node_id, data in self.backend._nodes.items():
            if data.get("_type") == "Company" and data.get("orgnr") == orgnr:
                return data
        return None

    async def find_person_by_personnummer(self, personnummer: str) -> Optional[dict]:
        """Find a person by personnummer."""
        if isinstance(self.backend, Neo4jBackend):
            return await self.backend.find_by_personnummer(personnummer)
        # NetworkX fallback
        for node_id, data in self.backend._nodes.items():
            if data.get("_type") == "Person" and data.get("personnummer") == personnummer:
                return data
        return None

    # Batch operations

    async def add_companies_batch(self, companies: list[Company]) -> list[str]:
        """Add multiple companies in a single transaction."""
        if isinstance(self.backend, Neo4jBackend):
            return await self.backend.create_nodes_batch(companies)
        # NetworkX fallback
        return [await self.add_company(c) for c in companies]

    async def add_persons_batch(self, persons: list[Person]) -> list[str]:
        """Add multiple persons in a single transaction."""
        if isinstance(self.backend, Neo4jBackend):
            return await self.backend.create_nodes_batch(persons)
        return [await self.add_person(p) for p in persons]

    # Statistics

    async def get_statistics(self) -> dict:
        """Get graph statistics."""
        if isinstance(self.backend, Neo4jBackend):
            return await self.backend.get_network_statistics()
        # NetworkX fallback
        return {
            "nodes": len(self.backend._nodes),
            "edges": len(self.backend._edges),
            "companies": sum(1 for n in self.backend._nodes.values() if n.get("_type") == "Company"),
            "persons": sum(1 for n in self.backend._nodes.values() if n.get("_type") == "Person"),
            "addresses": sum(1 for n in self.backend._nodes.values() if n.get("_type") == "Address"),
        }

    # Graph algorithms

    def compute_centrality(self) -> dict[str, dict[str, float]]:
        """Compute centrality metrics (NetworkX backend only)."""
        if isinstance(self.backend, NetworkXBackend):
            return self.backend.compute_centrality()
        raise NotImplementedError("Centrality computation only available with NetworkX backend")

    def find_connected_components(self) -> list[set[str]]:
        """Find connected components (NetworkX backend only)."""
        if isinstance(self.backend, NetworkXBackend):
            undirected = self.backend.graph.to_undirected()
            return [set(c) for c in nx.connected_components(undirected)]
        raise NotImplementedError("Component detection only available with NetworkX backend")

    def compute_network_metrics(self) -> dict[str, dict[str, float]]:
        """
        Compute network metrics for all nodes.

        Only available with NetworkX backend.
        """
        if isinstance(self.backend, NetworkXBackend):
            return self.backend.compute_centrality()
        raise NotImplementedError("Network metrics only available with NetworkX backend")

    def find_cycles(self, max_length: int = 6) -> list[list[str]]:
        """
        Find ownership cycles (circular ownership detection).

        Only available with NetworkX backend.
        """
        if isinstance(self.backend, NetworkXBackend):
            return self.backend.find_cycles(max_length)
        raise NotImplementedError("Cycle detection only available with NetworkX backend")


# Factory function

def create_graph_client(
    backend_type: str = "networkx",
    **kwargs
) -> GraphClient:
    """
    Create a graph client with the specified backend.

    Args:
        backend_type: One of "networkx", "neo4j", "age"
        **kwargs: Backend-specific configuration

    Returns:
        Configured GraphClient instance

    Examples:
        # NetworkX (default, for development/testing)
        client = create_graph_client("networkx")

        # Neo4j
        client = create_graph_client("neo4j",
            uri="bolt://localhost:7687",
            user="neo4j",
            password="password"
        )

        # Apache AGE (PostgreSQL graph extension)
        client = create_graph_client("age",
            host="localhost",
            port=5432,
            database="halo",
            user="postgres",
            password="password",
            graph_name="halo_graph"
        )
    """
    if backend_type == "networkx":
        backend = NetworkXBackend()
    elif backend_type == "neo4j":
        backend = Neo4jBackend(
            uri=kwargs.get("uri", "bolt://localhost:7687"),
            user=kwargs.get("user", "neo4j"),
            password=kwargs.get("password", ""),
            database=kwargs.get("database", "neo4j")
        )
    elif backend_type == "age":
        from halo.graph.age_backend import create_age_backend
        backend = create_age_backend(
            host=kwargs.get("host", "localhost"),
            port=kwargs.get("port", 5432),
            database=kwargs.get("database", "halo"),
            user=kwargs.get("user", "postgres"),
            password=kwargs.get("password", ""),
            graph_name=kwargs.get("graph_name", "halo_graph"),
        )
    else:
        raise ValueError(f"Unknown backend type: {backend_type}. Supported: networkx, neo4j, age")

    return GraphClient(backend)
