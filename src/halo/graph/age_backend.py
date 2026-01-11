"""
Apache AGE Backend for Halo Graph Module.

Apache AGE (A Graph Extension) is a PostgreSQL extension that adds graph database
capabilities, enabling Cypher queries alongside SQL in the same database.

This backend allows using PostgreSQL as both the relational and graph database,
simplifying the architecture and enabling transactional consistency.

Requirements:
- PostgreSQL with AGE extension installed
- asyncpg for async PostgreSQL access
"""

import json
import logging
from dataclasses import asdict
from datetime import datetime
from typing import Any, Optional

from halo.graph.client import GraphBackend, NodeType, EdgeType

logger = logging.getLogger(__name__)


class AgeBackend(GraphBackend):
    """
    Apache AGE backend for graph operations.

    Stores graph data in PostgreSQL using the AGE extension.
    Queries use Cypher syntax wrapped in ag_catalog functions.
    """

    # Graph name for the Halo intelligence graph
    DEFAULT_GRAPH = "halo_graph"

    # Node label to PostgreSQL property mappings
    NODE_PROPERTIES = {
        "Person": ["id", "name", "personnummer", "birth_year", "gender", "risk_score"],
        "Company": ["id", "name", "orgnr", "legal_form", "status", "registration_date",
                    "risk_score", "shell_score", "sni_codes"],
        "Address": ["id", "street", "street_number", "postal_code", "city",
                    "latitude", "longitude", "vulnerable_area"],
        "Property": ["id", "property_id", "type", "area", "address"],
        "BankAccount": ["id", "iban", "bic", "bank_name", "account_type"],
        "Document": ["id", "doc_type", "title", "source", "created_at"],
    }

    def __init__(
        self,
        connection_string: str,
        graph_name: str = DEFAULT_GRAPH,
        auto_setup: bool = True,
    ):
        """
        Initialize the AGE backend.

        Args:
            connection_string: PostgreSQL connection string
            graph_name: Name of the AGE graph to use
            auto_setup: Whether to create graph and indexes on connect
        """
        self.connection_string = connection_string
        self.graph_name = graph_name
        self.auto_setup = auto_setup
        self._pool = None
        self._setup_done = False

    async def connect(self) -> None:
        """Establish connection to PostgreSQL with AGE extension."""
        try:
            import asyncpg

            self._pool = await asyncpg.create_pool(
                self.connection_string,
                min_size=2,
                max_size=10,
            )

            # Test AGE extension is available
            async with self._pool.acquire() as conn:
                await conn.execute("LOAD 'age';")
                await conn.execute("SET search_path = ag_catalog, \"$user\", public;")

                # Check if our graph exists
                result = await conn.fetchval(
                    "SELECT EXISTS(SELECT 1 FROM ag_catalog.ag_graph WHERE name = $1)",
                    self.graph_name
                )

                if not result and self.auto_setup:
                    await self._setup_graph(conn)

            logger.info(f"Connected to PostgreSQL AGE with graph '{self.graph_name}'")

        except ImportError:
            raise ImportError("asyncpg package required. Install with: pip install asyncpg")
        except Exception as e:
            logger.error(f"Failed to connect to PostgreSQL AGE: {e}")
            raise

    async def _setup_graph(self, conn) -> None:
        """Create the graph and set up indexes."""
        logger.info(f"Creating AGE graph '{self.graph_name}'...")

        # Create the graph
        await conn.execute(f"SELECT create_graph('{self.graph_name}');")

        # Note: AGE doesn't support CREATE INDEX on vertex labels yet
        # Indexing is done at the PostgreSQL level on the underlying tables

        self._setup_done = True
        logger.info("AGE graph setup complete")

    async def close(self) -> None:
        """Close the connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None
            logger.info("PostgreSQL AGE connection closed")

    def _prepare_connection(self, conn) -> None:
        """Prepare a connection for AGE queries."""
        # Note: This is synchronous; called via run_sync in execute methods

    async def execute(self, query: str, params: Optional[dict] = None) -> list[dict]:
        """
        Execute a Cypher query via AGE.

        The query is wrapped in ag_catalog.cypher() function.

        Args:
            query: Cypher query string
            params: Query parameters (currently limited support in AGE)

        Returns:
            List of result dictionaries
        """
        if not self._pool:
            raise RuntimeError("Not connected to PostgreSQL AGE")

        async with self._pool.acquire() as conn:
            await conn.execute("LOAD 'age';")
            await conn.execute("SET search_path = ag_catalog, \"$user\", public;")

            # AGE requires wrapping Cypher in cypher() function
            # Parameters must be embedded (AGE has limited parameterized query support)
            wrapped_query = f"""
                SELECT * FROM cypher('{self.graph_name}', $$
                    {query}
                $$) AS (result agtype);
            """

            try:
                rows = await conn.fetch(wrapped_query)
                return [self._parse_agtype(row['result']) for row in rows]
            except Exception as e:
                logger.error(f"AGE query error: {e}\nQuery: {query}")
                raise

    def _parse_agtype(self, value: Any) -> dict:
        """Parse AGE agtype result into Python dict."""
        if value is None:
            return {}

        # agtype is returned as a string in JSON-like format
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return {"value": value}

        return {"value": value}

    def _escape_string(self, value: str) -> str:
        """Escape a string value for Cypher queries."""
        if value is None:
            return "null"
        # Escape single quotes by doubling them
        return value.replace("'", "''")

    def _format_properties(self, data: dict) -> str:
        """Format a dict as Cypher properties string."""
        parts = []
        for key, value in data.items():
            if value is None:
                continue
            if isinstance(value, str):
                parts.append(f"{key}: '{self._escape_string(value)}'")
            elif isinstance(value, bool):
                parts.append(f"{key}: {str(value).lower()}")
            elif isinstance(value, (int, float)):
                parts.append(f"{key}: {value}")
            elif isinstance(value, datetime):
                parts.append(f"{key}: '{value.isoformat()}'")
            elif isinstance(value, (list, dict)):
                # JSON-encode complex types
                json_str = json.dumps(value).replace("'", "''")
                parts.append(f"{key}: '{json_str}'")

        return ", ".join(parts)

    async def create_node(self, node: NodeType) -> str:
        """Create a node in the AGE graph."""
        node_type = type(node).__name__
        data = asdict(node)

        # Convert complex types for storage
        for key, value in list(data.items()):
            if isinstance(value, datetime):
                data[key] = value.isoformat()
            elif value is None:
                del data[key]

        props = self._format_properties(data)

        query = f"""
            MERGE (n:{node_type} {{id: '{data["id"]}'}})
            SET n = {{{props}}}
            RETURN n.id as id
        """

        result = await self.execute(query)
        return result[0].get("id", node.id) if result else node.id

    async def create_edge(self, edge: EdgeType) -> str:
        """Create an edge in the AGE graph."""
        edge_type = type(edge).__name__.replace("Edge", "").upper()
        data = asdict(edge)

        from_id = data.pop("from_id")
        to_id = data.pop("to_id")
        data.pop("from_type", None)

        # Convert complex types
        for key, value in list(data.items()):
            if isinstance(value, datetime):
                data[key] = value.isoformat()
            elif value is None:
                del data[key]

        props = self._format_properties(data)

        # Use MERGE to avoid duplicate edges
        query = f"""
            MATCH (a {{id: '{from_id}'}})
            MATCH (b {{id: '{to_id}'}})
            MERGE (a)-[r:{edge_type}]->(b)
            SET r = {{{props}}}
            RETURN r.id as id
        """

        result = await self.execute(query)
        return result[0].get("id", edge.id) if result else edge.id

    async def get_node(self, node_id: str, node_type: str) -> Optional[dict]:
        """Get a node by ID and type."""
        query = f"""
            MATCH (n:{node_type} {{id: '{self._escape_string(node_id)}'}})
            RETURN n
        """

        result = await self.execute(query)
        if not result:
            return None

        node = result[0].get("n", result[0])
        if isinstance(node, dict):
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
        edge_filter = ""
        if edge_types:
            rel_types = [t.replace("Edge", "").upper() for t in edge_types]
            edge_filter = ":" + "|".join(rel_types)

        safe_id = self._escape_string(node_id)

        if direction == "out":
            pattern = f"(n {{id: '{safe_id}'}})-[r{edge_filter}]->(m)"
        elif direction == "in":
            pattern = f"(n {{id: '{safe_id}'}})<-[r{edge_filter}]-(m)"
        else:
            pattern = f"(n {{id: '{safe_id}'}})-[r{edge_filter}]-(m)"

        query = f"""
            MATCH {pattern}
            RETURN m, type(r) as edge_type, properties(r) as edge
        """

        results = await self.execute(query)

        neighbors = []
        for row in results:
            node = row.get("m", {})
            if isinstance(node, dict):
                # Parse JSON fields
                for key, value in node.items():
                    if isinstance(value, str) and value.startswith(('[', '{')):
                        try:
                            node[key] = json.loads(value)
                        except json.JSONDecodeError:
                            pass

            edge_data = row.get("edge", {})
            if isinstance(edge_data, str):
                try:
                    edge_data = json.loads(edge_data)
                except json.JSONDecodeError:
                    edge_data = {}

            neighbors.append({
                "m": node,
                "edge_type": row.get("edge_type"),
                "edge": edge_data
            })

        return neighbors

    async def find_by_orgnr(self, orgnr: str) -> Optional[dict]:
        """Find a company by organisationsnummer."""
        query = f"""
            MATCH (c:Company {{orgnr: '{self._escape_string(orgnr)}'}})
            RETURN c
        """
        result = await self.execute(query)
        if result:
            return result[0].get("c", result[0])
        return None

    async def find_by_personnummer(self, personnummer: str) -> Optional[dict]:
        """Find a person by personnummer."""
        query = f"""
            MATCH (p:Person {{personnummer: '{self._escape_string(personnummer)}'}})
            RETURN p
        """
        result = await self.execute(query)
        if result:
            return result[0].get("p", result[0])
        return None

    async def get_companies_at_address(self, address_id: str) -> list[dict]:
        """Get all companies registered at an address."""
        query = f"""
            MATCH (c:Company)-[:REGISTEREDAT]->(a:Address {{id: '{self._escape_string(address_id)}'}})
            RETURN c
        """
        results = await self.execute(query)
        return [r.get("c", r) for r in results]

    async def get_directorships(self, person_id: str) -> list[dict]:
        """Get all companies a person directs."""
        query = f"""
            MATCH (p:Person {{id: '{self._escape_string(person_id)}'}})-[r:DIRECTS]->(c:Company)
            RETURN c, r.role as role
        """
        results = await self.execute(query)
        return [{"company": r.get("c", {}), "role": r.get("role")} for r in results]

    async def get_ownership_chain(self, company_id: str, max_depth: int = 10) -> list[dict]:
        """Traverse ownership chain to find beneficial owners."""
        # AGE supports variable-length paths with *
        query = f"""
            MATCH path = (start:Company {{id: '{self._escape_string(company_id)}'}})<-[:OWNS*1..{max_depth}]-(owner)
            RETURN owner, length(path) as depth
        """
        results = await self.execute(query)
        return [
            {
                "owner": r.get("owner", {}),
                "depth": r.get("depth", 0),
            }
            for r in results
        ]

    async def find_circular_ownership(self, max_length: int = 6) -> list[list[str]]:
        """Find circular ownership patterns."""
        query = f"""
            MATCH path = (c:Company)-[:OWNS*2..{max_length}]->(c)
            RETURN [n in nodes(path) | n.id] as cycle
            LIMIT 100
        """
        results = await self.execute(query)
        return [r.get("cycle", []) for r in results]

    async def get_network_statistics(self) -> dict:
        """Get overall graph statistics."""
        # Count nodes by type
        stats = {}
        for node_type in ["Person", "Company", "Address"]:
            query = f"""
                MATCH (n:{node_type})
                RETURN count(n) as count
            """
            result = await self.execute(query)
            if result:
                stats[node_type] = result[0].get("count", 0)

        # Count edges
        edge_query = """
            MATCH ()-[r]->()
            RETURN type(r) as rel_type, count(r) as count
        """
        try:
            edge_results = await self.execute(edge_query)
            for r in edge_results:
                rel_type = r.get("rel_type")
                if rel_type:
                    stats[rel_type] = r.get("count", 0)
        except Exception:
            pass  # Some AGE versions don't support this aggregation

        return stats

    async def execute_raw_sql(self, sql: str, params: Optional[tuple] = None) -> list[dict]:
        """
        Execute raw SQL query (for mixed SQL/Cypher operations).

        This allows combining relational queries with graph queries.
        """
        if not self._pool:
            raise RuntimeError("Not connected to PostgreSQL AGE")

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, *(params or ()))
            return [dict(row) for row in rows]


def create_age_backend(
    host: str = "localhost",
    port: int = 5432,
    database: str = "halo",
    user: str = "postgres",
    password: str = "",
    graph_name: str = "halo_graph",
) -> AgeBackend:
    """
    Factory function to create an AGE backend.

    Args:
        host: PostgreSQL host
        port: PostgreSQL port
        database: Database name
        user: Database user
        password: Database password
        graph_name: AGE graph name

    Returns:
        Configured AgeBackend instance
    """
    connection_string = f"postgresql://{user}:{password}@{host}:{port}/{database}"
    return AgeBackend(connection_string, graph_name)
