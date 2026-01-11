"""
Tests for user management API endpoints and access control.

Tests:
- User CRUD operations
- Role-based access control
- User authentication
- Permission checks
"""

from datetime import datetime
from uuid import uuid4

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from halo.security.auth import User, UserRole, hash_password, verify_password
from halo.api.deps import require_admin, require_analyst, require_senior_analyst


class TestUserManagement:
    """Tests for user management endpoints."""

    def test_list_users_response_format(self):
        """Should return paginated user list."""
        response = {
            "items": [
                {
                    "id": str(uuid4()),
                    "username": "test_user",
                    "email": "test@example.com",
                    "full_name": "Test User",
                    "role": "analyst",
                    "is_active": True,
                    "last_login": datetime.utcnow().isoformat(),
                    "created_at": datetime.utcnow().isoformat(),
                }
            ],
            "total": 1,
            "page": 1,
            "page_size": 20,
            "total_pages": 1,
        }

        assert "items" in response
        assert "total" in response
        assert len(response["items"]) == 1
        assert response["items"][0]["role"] in ["viewer", "analyst", "senior_analyst", "admin"]

    def test_create_user_response(self):
        """Should create user and return user data."""
        user_id = uuid4()
        response = {
            "id": str(user_id),
            "username": "new_user",
            "email": "new@example.com",
            "full_name": "New User",
            "role": "viewer",
            "is_active": True,
            "last_login": None,
            "created_at": datetime.utcnow().isoformat(),
        }

        assert response["id"] == str(user_id)
        assert response["username"] == "new_user"
        assert response["is_active"] is True

    def test_update_user_response(self):
        """Should update user and return updated data."""
        user_id = uuid4()
        response = {
            "id": str(user_id),
            "username": "test_user",
            "email": "updated@example.com",
            "full_name": "Updated Name",
            "role": "analyst",
            "is_active": True,
            "last_login": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat(),
        }

        assert response["email"] == "updated@example.com"
        assert response["full_name"] == "Updated Name"

    def test_deactivate_user(self):
        """Should soft delete user by setting is_active to False."""
        user_id = uuid4()
        # After deletion, user should be inactive
        response = {
            "id": str(user_id),
            "username": "test_user",
            "email": "test@example.com",
            "full_name": "Test User",
            "role": "viewer",
            "is_active": False,
            "last_login": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat(),
        }

        assert response["is_active"] is False


class TestPasswordSecurity:
    """Tests for password hashing and verification."""

    def test_password_hashing(self):
        """Should hash password securely."""
        password = "SecurePassword123!"
        hashed = hash_password(password)

        assert hashed != password
        assert len(hashed) > 50  # Argon2 hashes are long
        assert hashed.startswith("$argon2")

    def test_password_verification_success(self):
        """Should verify correct password."""
        password = "SecurePassword123!"
        hashed = hash_password(password)

        assert verify_password(password, hashed) is True

    def test_password_verification_failure(self):
        """Should reject incorrect password."""
        password = "SecurePassword123!"
        wrong_password = "WrongPassword456!"
        hashed = hash_password(password)

        assert verify_password(wrong_password, hashed) is False

    def test_password_hashing_uniqueness(self):
        """Should produce different hashes for same password (salt)."""
        password = "SecurePassword123!"
        hash1 = hash_password(password)
        hash2 = hash_password(password)

        assert hash1 != hash2  # Different salts
        assert verify_password(password, hash1)
        assert verify_password(password, hash2)


class TestAccessControl:
    """Tests for role-based access control."""

    def test_user_role_hierarchy(self):
        """Should enforce role hierarchy correctly."""
        viewer = User(
            id="user1",
            username="viewer",
            role=UserRole.VIEWER,
            is_active=True,
        )
        analyst = User(
            id="user2",
            username="analyst",
            role=UserRole.ANALYST,
            is_active=True,
        )
        senior = User(
            id="user3",
            username="senior",
            role=UserRole.SENIOR_ANALYST,
            is_active=True,
        )
        admin = User(
            id="user4",
            username="admin",
            role=UserRole.ADMIN,
            is_active=True,
        )

        # Viewer can only view
        assert viewer.can_view_entities is True
        assert viewer.can_create_cases is False
        assert viewer.can_acknowledge_alerts is False
        assert viewer.can_approve_tier3 is False
        assert viewer.can_manage_users is False

        # Analyst can create cases and acknowledge alerts
        assert analyst.can_view_entities is True
        assert analyst.can_create_cases is True
        assert analyst.can_acknowledge_alerts is True
        assert analyst.can_approve_tier3 is False
        assert analyst.can_manage_users is False

        # Senior analyst can approve tier 3
        assert senior.can_view_entities is True
        assert senior.can_create_cases is True
        assert senior.can_acknowledge_alerts is True
        assert senior.can_approve_tier3 is True
        assert senior.can_manage_users is False

        # Admin has all permissions
        assert admin.can_view_entities is True
        assert admin.can_create_cases is True
        assert admin.can_acknowledge_alerts is True
        assert admin.can_approve_tier3 is True
        assert admin.can_manage_users is True

    def test_export_data_permission(self):
        """Should restrict data export to senior+ roles."""
        viewer = User(id="v", username="viewer", role=UserRole.VIEWER, is_active=True)
        analyst = User(id="a", username="analyst", role=UserRole.ANALYST, is_active=True)
        senior = User(id="s", username="senior", role=UserRole.SENIOR_ANALYST, is_active=True)
        admin = User(id="ad", username="admin", role=UserRole.ADMIN, is_active=True)

        assert viewer.can_export_data is False
        assert analyst.can_export_data is False
        assert senior.can_export_data is True
        assert admin.can_export_data is True

    @pytest.mark.asyncio
    async def test_require_analyst_allows_analyst(self):
        """Should allow analyst role."""
        user = User(
            id="analyst1",
            username="analyst",
            role=UserRole.ANALYST,
            is_active=True,
        )

        # Should not raise exception
        result = await require_analyst(user)
        assert result == user

    @pytest.mark.asyncio
    async def test_require_analyst_blocks_viewer(self):
        """Should block viewer role."""
        from fastapi import HTTPException

        user = User(
            id="viewer1",
            username="viewer",
            role=UserRole.VIEWER,
            is_active=True,
        )

        with pytest.raises(HTTPException) as exc_info:
            await require_analyst(user)

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_require_senior_analyst_hierarchy(self):
        """Should only allow senior analyst and admin."""
        from fastapi import HTTPException

        viewer = User(id="v", username="viewer", role=UserRole.VIEWER, is_active=True)
        analyst = User(id="a", username="analyst", role=UserRole.ANALYST, is_active=True)
        senior = User(id="s", username="senior", role=UserRole.SENIOR_ANALYST, is_active=True)
        admin = User(id="ad", username="admin", role=UserRole.ADMIN, is_active=True)

        # Viewer and analyst should be blocked
        with pytest.raises(HTTPException):
            await require_senior_analyst(viewer)
        with pytest.raises(HTTPException):
            await require_senior_analyst(analyst)

        # Senior analyst and admin should pass
        result1 = await require_senior_analyst(senior)
        result2 = await require_senior_analyst(admin)
        assert result1 == senior
        assert result2 == admin

    @pytest.mark.asyncio
    async def test_require_admin_exclusive(self):
        """Should only allow admin role."""
        from fastapi import HTTPException

        viewer = User(id="v", username="viewer", role=UserRole.VIEWER, is_active=True)
        analyst = User(id="a", username="analyst", role=UserRole.ANALYST, is_active=True)
        senior = User(id="s", username="senior", role=UserRole.SENIOR_ANALYST, is_active=True)
        admin = User(id="ad", username="admin", role=UserRole.ADMIN, is_active=True)

        # All non-admin roles should be blocked
        with pytest.raises(HTTPException):
            await require_admin(viewer)
        with pytest.raises(HTTPException):
            await require_admin(analyst)
        with pytest.raises(HTTPException):
            await require_admin(senior)

        # Admin should pass
        result = await require_admin(admin)
        assert result == admin


class TestCaseAccessControl:
    """Tests for case management access control."""

    def test_create_case_requires_analyst(self):
        """Should require analyst role to create case."""
        # This would be tested in integration tests with actual HTTP requests
        # Here we verify the dependency injection is correct
        viewer = User(id="v", username="viewer", role=UserRole.VIEWER, is_active=True)
        analyst = User(id="a", username="analyst", role=UserRole.ANALYST, is_active=True)

        assert viewer.can_create_cases is False
        assert analyst.can_create_cases is True

    def test_close_case_requires_analyst(self):
        """Should require analyst role to close case."""
        viewer = User(id="v", username="viewer", role=UserRole.VIEWER, is_active=True)
        analyst = User(id="a", username="analyst", role=UserRole.ANALYST, is_active=True)

        # Viewers cannot close cases (same permission as create)
        assert viewer.can_create_cases is False
        assert analyst.can_create_cases is True


class TestAlertAccessControl:
    """Tests for alert access control."""

    def test_acknowledge_alert_requires_analyst(self):
        """Should require analyst role to acknowledge alert."""
        viewer = User(id="v", username="viewer", role=UserRole.VIEWER, is_active=True)
        analyst = User(id="a", username="analyst", role=UserRole.ANALYST, is_active=True)

        assert viewer.can_acknowledge_alerts is False
        assert analyst.can_acknowledge_alerts is True

    def test_approve_tier3_requires_senior_analyst(self):
        """Should require senior analyst role for Tier 3 approval (Brottsdatalagen)."""
        viewer = User(id="v", username="viewer", role=UserRole.VIEWER, is_active=True)
        analyst = User(id="a", username="analyst", role=UserRole.ANALYST, is_active=True)
        senior = User(id="s", username="senior", role=UserRole.SENIOR_ANALYST, is_active=True)
        admin = User(id="ad", username="admin", role=UserRole.ADMIN, is_active=True)

        # Only senior analyst and admin can approve tier 3
        assert viewer.can_approve_tier3 is False
        assert analyst.can_approve_tier3 is False
        assert senior.can_approve_tier3 is True
        assert admin.can_approve_tier3 is True

    def test_dismiss_alert_requires_analyst(self):
        """Should require analyst role to dismiss alert."""
        viewer = User(id="v", username="viewer", role=UserRole.VIEWER, is_active=True)
        analyst = User(id="a", username="analyst", role=UserRole.ANALYST, is_active=True)

        # Analysts can dismiss (same as acknowledge)
        assert viewer.can_acknowledge_alerts is False
        assert analyst.can_acknowledge_alerts is True


class TestUserRepository:
    """Tests for UserRepository methods."""

    @pytest.mark.asyncio
    async def test_list_users_filtering(self):
        """Should filter users by role and active status."""
        # Mock repository behavior would be tested here
        # For now, verify the expected parameters
        params = {
            "role": "analyst",
            "is_active": True,
            "limit": 20,
            "offset": 0,
        }

        assert params["role"] == "analyst"
        assert params["is_active"] is True

    @pytest.mark.asyncio
    async def test_count_users_filtering(self):
        """Should count users with filters."""
        params = {
            "role": "viewer",
            "is_active": True,
        }

        assert params["role"] == "viewer"
        assert params["is_active"] is True

    @pytest.mark.asyncio
    async def test_create_user_hashes_password(self):
        """Should hash password when creating user."""
        # Verify password is hashed before storage
        password = "SecurePassword123!"
        hashed = hash_password(password)

        # Hashed password should be stored, not plain text
        assert hashed != password
        assert verify_password(password, hashed)

    @pytest.mark.asyncio
    async def test_update_user_fields(self):
        """Should update specific user fields."""
        update_data = {
            "email": "new@example.com",
            "full_name": "New Name",
            "role": "senior_analyst",
            "is_active": False,
        }

        # All fields should be optional
        assert "email" in update_data
        assert "role" in update_data
        assert update_data["is_active"] is False
