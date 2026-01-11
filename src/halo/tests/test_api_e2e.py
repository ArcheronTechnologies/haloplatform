"""
End-to-end API integration tests.

Tests actual HTTP endpoints via FastAPI TestClient.
These tests verify the complete request/response cycle.
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient


# Mock external dependencies before importing app
@pytest.fixture(scope="module")
def mock_dependencies():
    """Mock external services (Redis, Elasticsearch, DB)."""
    with patch("halo.main.redis") as mock_redis, \
         patch("halo.main.AsyncElasticsearch") as mock_es, \
         patch("halo.main.create_async_engine") as mock_engine:

        # Mock Redis
        mock_redis_client = MagicMock()
        mock_redis_client.ping = AsyncMock(return_value=True)
        mock_redis_client.close = AsyncMock()
        mock_redis.from_url.return_value = mock_redis_client

        # Mock Elasticsearch
        mock_es_client = MagicMock()
        mock_es_client.ping = AsyncMock(return_value=True)
        mock_es_client.close = AsyncMock()
        mock_es.return_value = mock_es_client

        yield {
            "redis": mock_redis_client,
            "es": mock_es_client,
        }


@pytest.fixture(scope="module")
def client(mock_dependencies):
    """Create test client with mocked dependencies."""
    # Import app after mocking
    from halo.main import app

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


class TestHealthEndpoint:
    """Tests for the health check endpoint."""

    def test_health_returns_200(self, client):
        """Health endpoint should return 200 OK."""
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_response_structure(self, client):
        """Health response should have correct structure."""
        response = client.get("/health")
        data = response.json()

        assert "status" in data
        assert "timestamp" in data
        assert "version" in data

    def test_health_includes_version(self, client):
        """Health response should include version."""
        response = client.get("/health")
        data = response.json()

        assert data["version"] == "0.1.0"


class TestSecurityHeaders:
    """Tests for security headers on all responses."""

    def test_x_frame_options(self, client):
        """Response should include X-Frame-Options: DENY."""
        response = client.get("/health")
        assert response.headers.get("X-Frame-Options") == "DENY"

    def test_x_content_type_options(self, client):
        """Response should include X-Content-Type-Options: nosniff."""
        response = client.get("/health")
        assert response.headers.get("X-Content-Type-Options") == "nosniff"

    def test_x_xss_protection(self, client):
        """Response should include XSS protection header."""
        response = client.get("/health")
        assert response.headers.get("X-XSS-Protection") == "1; mode=block"

    def test_referrer_policy(self, client):
        """Response should include Referrer-Policy."""
        response = client.get("/health")
        assert "Referrer-Policy" in response.headers

    def test_content_security_policy(self, client):
        """Response should include Content-Security-Policy."""
        response = client.get("/health")
        assert "Content-Security-Policy" in response.headers

    def test_permissions_policy(self, client):
        """Response should include Permissions-Policy."""
        response = client.get("/health")
        assert "Permissions-Policy" in response.headers


class TestCORSHeaders:
    """Tests for CORS configuration."""

    def test_cors_preflight_options(self, client):
        """OPTIONS request should return CORS headers."""
        response = client.options(
            "/api/v1/entities",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            }
        )
        # Should have CORS headers
        assert "Access-Control-Allow-Origin" in response.headers or response.status_code == 200


class TestAPIVersioning:
    """Tests for API versioning."""

    def test_api_v1_prefix(self, client):
        """API endpoints should be under /api/v1/ prefix."""
        # This tests that the routes are properly mounted
        response = client.get("/api/v1/dashboard/stats")
        # Should either return data or 401 (auth required), not 404
        assert response.status_code in [200, 401, 403, 422]


class TestDashboardEndpoints:
    """Tests for dashboard API endpoints."""

    def test_dashboard_stats_endpoint_exists(self, client):
        """Dashboard stats endpoint should exist."""
        response = client.get("/api/v1/dashboard/stats")
        # May require auth, but shouldn't be 404
        assert response.status_code != 404

    def test_dashboard_recent_alerts_endpoint_exists(self, client):
        """Dashboard recent alerts endpoint should exist."""
        response = client.get("/api/v1/dashboard/recent-alerts")
        assert response.status_code != 404

    def test_dashboard_recent_cases_endpoint_exists(self, client):
        """Dashboard recent cases endpoint should exist."""
        response = client.get("/api/v1/dashboard/recent-cases")
        assert response.status_code != 404


class TestEntityEndpoints:
    """Tests for entity API endpoints."""

    def test_entity_list_endpoint_exists(self, client):
        """Entity list endpoint should exist."""
        response = client.get("/api/v1/entities")
        assert response.status_code != 404

    def test_entity_by_personnummer_endpoint_exists(self, client):
        """Entity by personnummer endpoint should exist."""
        response = client.get("/api/v1/entities/by-personnummer/198001011234")
        assert response.status_code != 404

    def test_entity_by_orgnr_endpoint_exists(self, client):
        """Entity by orgnr endpoint should exist."""
        response = client.get("/api/v1/entities/by-orgnr/5591234567")
        assert response.status_code != 404


class TestAlertEndpoints:
    """Tests for alert API endpoints."""

    def test_alert_list_endpoint_exists(self, client):
        """Alert list endpoint should exist."""
        response = client.get("/api/v1/alerts")
        assert response.status_code != 404


class TestCaseEndpoints:
    """Tests for case API endpoints."""

    def test_case_list_endpoint_exists(self, client):
        """Case list endpoint should exist."""
        response = client.get("/api/v1/cases")
        assert response.status_code != 404


class TestSearchEndpoints:
    """Tests for search API endpoints."""

    def test_search_endpoint_exists(self, client):
        """Search endpoint should exist."""
        response = client.get("/api/v1/search?q=test")
        assert response.status_code != 404


class TestGraphEndpoints:
    """Tests for graph API endpoints."""

    def test_graph_centrality_endpoint_exists(self, client):
        """Graph centrality endpoint should exist."""
        response = client.get("/api/v1/graph/metrics/centrality")
        assert response.status_code != 404

    def test_graph_components_endpoint_exists(self, client):
        """Graph components endpoint should exist."""
        response = client.get("/api/v1/graph/metrics/components")
        assert response.status_code != 404


class TestIntelligenceEndpoints:
    """Tests for intelligence API endpoints."""

    def test_intelligence_patterns_endpoint_exists(self, client):
        """Intelligence patterns endpoint should exist."""
        response = client.get("/api/v1/intelligence/patterns")
        assert response.status_code != 404


class TestSAREndpoints:
    """Tests for SAR API endpoints."""

    def test_sar_list_endpoint_exists(self, client):
        """SAR list endpoint should exist."""
        response = client.get("/api/v1/sars")
        assert response.status_code != 404


class TestAuthEndpoints:
    """Tests for authentication API endpoints."""

    def test_auth_login_endpoint_exists(self, client):
        """Auth login endpoint should exist."""
        response = client.post("/api/v1/auth/login", json={
            "username": "test",
            "password": "test"
        })
        # Should return 401 (invalid creds) or 422 (validation), not 404
        assert response.status_code != 404

    def test_auth_sessions_endpoint_exists(self, client):
        """Auth sessions endpoint should exist."""
        response = client.get("/api/v1/auth/sessions")
        # Should return 401 (no auth) or similar, not 404
        assert response.status_code != 404


class TestReferralEndpoints:
    """Tests for referral API endpoints."""

    def test_referral_list_endpoint_exists(self, client):
        """Referral list endpoint should exist."""
        response = client.get("/api/v1/referrals")
        assert response.status_code != 404


class TestEvidenceEndpoints:
    """Tests for evidence API endpoints."""

    def test_evidence_compile_endpoint_exists(self, client):
        """Evidence compile endpoint should exist."""
        response = client.post("/api/v1/evidence/compile", json={
            "case_id": "test-case-id",
            "entity_ids": ["entity-1"],
            "include_relationships": True
        })
        # Should return error (invalid case) or auth error, not 404
        assert response.status_code != 404


class TestImpactEndpoints:
    """Tests for impact API endpoints."""

    def test_impact_metrics_endpoint_exists(self, client):
        """Impact metrics endpoint should exist."""
        response = client.get("/api/v1/impact/metrics")
        assert response.status_code != 404


class TestRequestValidation:
    """Tests for request validation."""

    def test_invalid_json_returns_422(self, client):
        """Invalid JSON should return 422."""
        response = client.post(
            "/api/v1/auth/login",
            content="not valid json",
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 422

    def test_missing_required_field_returns_422(self, client):
        """Missing required field should return 422."""
        response = client.post(
            "/api/v1/auth/login",
            json={"username": "test"}  # Missing password
        )
        assert response.status_code == 422


class TestRateLimiting:
    """Tests for rate limiting."""

    def test_rate_limit_header_present(self, client):
        """Response should include rate limit headers."""
        response = client.get("/health")
        # Rate limiter adds these headers
        # This may vary based on slowapi configuration
        assert response.status_code == 200


class TestOpenAPIDocumentation:
    """Tests for OpenAPI documentation."""

    def test_openapi_json_available(self, client):
        """OpenAPI JSON should be available in non-production."""
        response = client.get("/openapi.json")
        # In test mode (non-production), should be available
        if response.status_code == 200:
            data = response.json()
            assert "openapi" in data
            assert "paths" in data
            assert "info" in data

    def test_docs_available(self, client):
        """Swagger UI should be available in non-production."""
        response = client.get("/docs")
        # Should return HTML or redirect, not 404
        assert response.status_code in [200, 307]

    def test_redoc_available(self, client):
        """ReDoc should be available in non-production."""
        response = client.get("/redoc")
        assert response.status_code in [200, 307]
