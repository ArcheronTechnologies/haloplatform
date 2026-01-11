"""
Tests for the graph client module.
"""

import pytest
from datetime import date

from halo.graph.client import (
    GraphClient,
    NetworkXBackend,
    create_graph_client,
)
from halo.graph.schema import Person, Company, Address
from halo.graph.edges import DirectsEdge, OwnsEdge, RegisteredAtEdge


class TestNetworkXBackend:
    """Tests for NetworkX backend."""

    @pytest.fixture
    def backend(self):
        """Create a fresh backend for each test."""
        return NetworkXBackend()

    @pytest.mark.asyncio
    async def test_connect_close(self, backend):
        """Test connect and close."""
        await backend.connect()
        assert backend.graph is not None

        await backend.close()
        assert len(backend.graph.nodes) == 0

    @pytest.mark.asyncio
    async def test_create_node(self, backend):
        """Test node creation."""
        await backend.connect()

        person = Person(
            id="test-person-1",
            personnummer="198501011234",
            names=[{"name": "Test Person"}]
        )

        node_id = await backend.create_node(person)

        assert node_id == "test-person-1"
        assert "test-person-1" in backend.graph.nodes
        assert backend._nodes["test-person-1"]["_type"] == "Person"

    @pytest.mark.asyncio
    async def test_create_edge(self, backend):
        """Test edge creation."""
        await backend.connect()

        # Create nodes first
        person = Person(id="person-1")
        company = Company(id="company-1")
        await backend.create_node(person)
        await backend.create_node(company)

        # Create edge
        edge = DirectsEdge(
            id="edge-1",
            from_id="person-1",
            to_id="company-1",
            role="styrelseledamot"
        )
        edge_id = await backend.create_edge(edge)

        assert edge_id == "edge-1"
        assert backend.graph.has_edge("person-1", "company-1")

    @pytest.mark.asyncio
    async def test_get_node(self, backend):
        """Test node retrieval."""
        await backend.connect()

        company = Company(
            id="company-1",
            orgnr="5560125790",
            names=[{"name": "Test AB"}]
        )
        await backend.create_node(company)

        retrieved = await backend.get_node("company-1", "Company")
        assert retrieved is not None
        assert retrieved["orgnr"] == "5560125790"

        # Wrong type should return None
        wrong_type = await backend.get_node("company-1", "Person")
        assert wrong_type is None

    @pytest.mark.asyncio
    async def test_get_neighbors(self, backend):
        """Test neighbor retrieval."""
        await backend.connect()

        # Create graph: person -> company -> address
        person = Person(id="person-1")
        company = Company(id="company-1")
        address = Address(id="address-1")

        await backend.create_node(person)
        await backend.create_node(company)
        await backend.create_node(address)

        directs = DirectsEdge(id="e1", from_id="person-1", to_id="company-1")
        registered = RegisteredAtEdge(id="e2", from_id="company-1", to_id="address-1")

        await backend.create_edge(directs)
        await backend.create_edge(registered)

        # Get neighbors of company
        neighbors = await backend.get_neighbors("company-1")
        assert len(neighbors) == 2  # person (in) and address (out)

        # Get only outgoing
        out_neighbors = await backend.get_neighbors("company-1", direction="out")
        assert len(out_neighbors) == 1
        assert out_neighbors[0]["m"]["id"] == "address-1"

    @pytest.mark.asyncio
    async def test_compute_centrality(self, backend):
        """Test centrality computation."""
        await backend.connect()

        # Create a small network
        for i in range(5):
            await backend.create_node(Company(id=f"company-{i}"))

        # Create edges
        edges = [
            OwnsEdge(id="e1", from_id="company-0", from_type="company", to_id="company-1"),
            OwnsEdge(id="e2", from_id="company-0", from_type="company", to_id="company-2"),
            OwnsEdge(id="e3", from_id="company-1", from_type="company", to_id="company-3"),
            OwnsEdge(id="e4", from_id="company-2", from_type="company", to_id="company-3"),
            OwnsEdge(id="e5", from_id="company-3", from_type="company", to_id="company-4"),
        ]
        for edge in edges:
            await backend.create_edge(edge)

        centrality = backend.compute_centrality()

        assert "degree" in centrality
        assert "betweenness" in centrality
        assert "pagerank" in centrality
        assert len(centrality["degree"]) == 5

    @pytest.mark.asyncio
    async def test_find_cycles(self, backend):
        """Test cycle detection."""
        await backend.connect()

        # Create a cycle: A -> B -> C -> A
        for i in ["A", "B", "C"]:
            await backend.create_node(Company(id=f"company-{i}"))

        edges = [
            OwnsEdge(id="e1", from_id="company-A", from_type="company", to_id="company-B"),
            OwnsEdge(id="e2", from_id="company-B", from_type="company", to_id="company-C"),
            OwnsEdge(id="e3", from_id="company-C", from_type="company", to_id="company-A"),
        ]
        for edge in edges:
            await backend.create_edge(edge)

        cycles = backend.find_cycles()
        assert len(cycles) >= 1
        assert len(cycles[0]) == 3


class TestGraphClient:
    """Tests for GraphClient."""

    @pytest.fixture
    def client(self):
        """Create a graph client with NetworkX backend."""
        return GraphClient()

    @pytest.mark.asyncio
    async def test_context_manager(self, client):
        """Test async context manager."""
        async with client:
            assert client._connected is True
        assert client._connected is False

    @pytest.mark.asyncio
    async def test_add_and_get_person(self, client):
        """Test adding and retrieving a person."""
        async with client:
            person = Person(
                id="person-test",
                personnummer="198501011234",
                names=[{"name": "Test Testsson"}]
            )
            await client.add_person(person)

            retrieved = await client.get_person("person-test")
            assert retrieved is not None
            assert retrieved["personnummer"] == "198501011234"

    @pytest.mark.asyncio
    async def test_add_and_get_company(self, client):
        """Test adding and retrieving a company."""
        async with client:
            company = Company(
                id="company-test",
                orgnr="5560125790",
                names=[{"name": "Volvo AB"}],
                legal_form="AB"
            )
            await client.add_company(company)

            retrieved = await client.get_company("company-test")
            assert retrieved is not None
            assert retrieved["orgnr"] == "5560125790"

    @pytest.mark.asyncio
    async def test_add_directorship(self, client):
        """Test adding directorship relationship."""
        async with client:
            person = Person(id="person-1")
            company = Company(id="company-1")
            await client.add_person(person)
            await client.add_company(company)

            edge = DirectsEdge(
                from_id="person-1",
                to_id="company-1",
                role="vd",
                from_date=date(2020, 1, 1)
            )
            await client.add_directorship(edge)

            # Verify through get_directorships
            directorships = await client.get_directorships("person-1")
            assert len(directorships) == 1
            assert directorships[0]["role"] == "vd"

    @pytest.mark.asyncio
    async def test_expand_network(self, client):
        """Test network expansion."""
        async with client:
            # Create a small network
            person = Person(id="person-1")
            company1 = Company(id="company-1")
            company2 = Company(id="company-2")
            address = Address(id="address-1")

            await client.add_person(person)
            await client.add_company(company1)
            await client.add_company(company2)
            await client.add_address(address)

            # Create relationships
            await client.add_directorship(DirectsEdge(
                from_id="person-1", to_id="company-1", role="vd"
            ))
            await client.add_directorship(DirectsEdge(
                from_id="person-1", to_id="company-2", role="styrelseledamot"
            ))
            await client.add_registration(RegisteredAtEdge(
                from_id="company-1", to_id="address-1", type="registered"
            ))

            # Expand from person
            network = await client.expand_network(["person-1"], hops=2)

            assert len(network["nodes"]) >= 2  # At least companies
            assert len(network["edges"]) >= 2

    @pytest.mark.asyncio
    async def test_get_companies_at_address(self, client):
        """Test getting companies at an address."""
        async with client:
            address = Address(id="address-1")
            company1 = Company(id="company-1")
            company2 = Company(id="company-2")

            await client.add_address(address)
            await client.add_company(company1)
            await client.add_company(company2)

            await client.add_registration(RegisteredAtEdge(
                from_id="company-1", to_id="address-1", type="registered"
            ))
            await client.add_registration(RegisteredAtEdge(
                from_id="company-2", to_id="address-1", type="registered"
            ))

            companies = await client.get_companies_at_address("address-1")
            assert len(companies) == 2

    @pytest.mark.asyncio
    async def test_get_ownership_chain(self, client):
        """Test ownership chain traversal."""
        async with client:
            # Create ownership chain: person -> company-a -> company-b -> company-c
            person = Person(id="person-1")
            company_a = Company(id="company-a")
            company_b = Company(id="company-b")
            company_c = Company(id="company-c")

            await client.add_person(person)
            await client.add_company(company_a)
            await client.add_company(company_b)
            await client.add_company(company_c)

            await client.add_ownership(OwnsEdge(
                from_id="person-1", from_type="person", to_id="company-a", share=100
            ))
            await client.add_ownership(OwnsEdge(
                from_id="company-a", from_type="company", to_id="company-b", share=100
            ))
            await client.add_ownership(OwnsEdge(
                from_id="company-b", from_type="company", to_id="company-c", share=100
            ))

            chain = await client.get_ownership_chain("company-c")
            assert len(chain) >= 1

    @pytest.mark.asyncio
    async def test_compute_network_metrics(self, client):
        """Test network metrics computation."""
        async with client:
            # Create some nodes
            for i in range(3):
                await client.add_company(Company(id=f"company-{i}"))

            await client.add_ownership(OwnsEdge(
                from_id="company-0", from_type="company", to_id="company-1"
            ))
            await client.add_ownership(OwnsEdge(
                from_id="company-1", from_type="company", to_id="company-2"
            ))

            metrics = client.compute_network_metrics()
            assert "degree" in metrics
            assert "betweenness" in metrics

    @pytest.mark.asyncio
    async def test_find_cycles(self, client):
        """Test cycle detection through client."""
        async with client:
            for i in ["A", "B", "C"]:
                await client.add_company(Company(id=f"company-{i}"))

            await client.add_ownership(OwnsEdge(
                from_id="company-A", from_type="company", to_id="company-B"
            ))
            await client.add_ownership(OwnsEdge(
                from_id="company-B", from_type="company", to_id="company-C"
            ))
            await client.add_ownership(OwnsEdge(
                from_id="company-C", from_type="company", to_id="company-A"
            ))

            cycles = client.find_cycles()
            assert len(cycles) >= 1


class TestGraphClientFactory:
    """Tests for graph client factory."""

    def test_create_networkx_client(self):
        """Test creating NetworkX client."""
        client = create_graph_client("networkx")
        assert isinstance(client.backend, NetworkXBackend)

    def test_create_unknown_backend(self):
        """Test creating unknown backend raises error."""
        with pytest.raises(ValueError):
            create_graph_client("unknown_backend")
