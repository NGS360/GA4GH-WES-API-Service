"""Tests for security utilities."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from fastapi import HTTPException
from fastapi.security import HTTPBasicCredentials, HTTPAuthorizationCredentials

from src.wes_service.core.security import (
    get_current_user,
    validate_api_token,
    verify_password,
    get_password_hash,
    parse_basic_auth_users,
)


class TestVerifyPassword:
    """Tests for password verification."""

    @patch("src.wes_service.core.security.pwd_context")
    def test_verify_correct_password(self, mock_ctx):
        """Correct password should verify successfully."""
        mock_ctx.verify.return_value = True
        assert verify_password("mysecret", "$2b$12$fakehash") is True
        mock_ctx.verify.assert_called_once_with("mysecret", "$2b$12$fakehash")

    @patch("src.wes_service.core.security.pwd_context")
    def test_verify_wrong_password(self, mock_ctx):
        """Wrong password should fail verification."""
        mock_ctx.verify.return_value = False
        assert verify_password("wrongpassword", "$2b$12$fakehash") is False
        mock_ctx.verify.assert_called_once_with("wrongpassword", "$2b$12$fakehash")


class TestGetPasswordHash:
    """Tests for password hashing."""

    @patch("src.wes_service.core.security.pwd_context")
    def test_returns_hash(self, mock_ctx):
        """get_password_hash should return the hashed value."""
        mock_ctx.hash.return_value = "$2b$12$hashedvalue"
        result = get_password_hash("mysecret")
        assert result == "$2b$12$hashedvalue"
        mock_ctx.hash.assert_called_once_with("mysecret")


class TestParseBasicAuthUsers:
    """Tests for parsing basic auth user configuration."""

    def test_empty_config(self):
        """Empty config should return empty dict."""
        with patch("src.wes_service.core.security.get_settings") as mock_settings:
            mock_settings.return_value.basic_auth_users = ""
            users = parse_basic_auth_users()
            assert users == {}

    def test_single_user(self):
        """Single user entry should be parsed correctly."""
        with patch("src.wes_service.core.security.get_settings") as mock_settings:
            mock_settings.return_value.basic_auth_users = "alice:$2b$12$somehash"
            users = parse_basic_auth_users()
            assert "alice" in users
            assert users["alice"] == "$2b$12$somehash"

    def test_multiple_users(self):
        """Multiple user entries should be parsed correctly."""
        with patch("src.wes_service.core.security.get_settings") as mock_settings:
            mock_settings.return_value.basic_auth_users = (
                "alice:$2b$12$hash1,bob:$2b$12$hash2"
            )
            users = parse_basic_auth_users()
            assert len(users) == 2
            assert "alice" in users
            assert "bob" in users
            assert users["alice"] == "$2b$12$hash1"
            assert users["bob"] == "$2b$12$hash2"

    def test_whitespace_handling(self):
        """Whitespace around entries should be stripped."""
        with patch("src.wes_service.core.security.get_settings") as mock_settings:
            mock_settings.return_value.basic_auth_users = (
                " alice : $2b$12$hash1 , bob : $2b$12$hash2 "
            )
            users = parse_basic_auth_users()
            assert "alice" in users
            assert "bob" in users


class TestGetCurrentUserNoneAuth:
    """Tests for get_current_user with auth_method='none'."""

    @pytest.mark.asyncio
    async def test_returns_anonymous(self):
        """When auth_method is 'none', should return 'anonymous'."""
        with patch("src.wes_service.core.security.get_settings") as mock_settings:
            mock_settings.return_value.auth_method = "none"

            result = await get_current_user(
                basic_credentials=None,
                bearer_credentials=None,
            )
            assert result == "anonymous"

    @pytest.mark.asyncio
    async def test_returns_anonymous_even_with_credentials(self):
        """When auth_method is 'none', should return 'anonymous' even if credentials provided."""
        with patch("src.wes_service.core.security.get_settings") as mock_settings:
            mock_settings.return_value.auth_method = "none"

            basic_creds = HTTPBasicCredentials(username="alice", password="pass")
            result = await get_current_user(
                basic_credentials=basic_creds,
                bearer_credentials=None,
            )
            assert result == "anonymous"


class TestGetCurrentUserBasicAuth:
    """Tests for get_current_user with auth_method='basic'."""

    @pytest.mark.asyncio
    @patch("src.wes_service.core.security.verify_password", return_value=True)
    async def test_valid_basic_credentials(self, mock_verify):
        """Valid basic credentials should return username."""
        with patch("src.wes_service.core.security.get_settings") as mock_settings:
            mock_settings.return_value.auth_method = "basic"
            mock_settings.return_value.basic_auth_users = "alice:$2b$12$hashedpwd"

            basic_creds = HTTPBasicCredentials(username="alice", password="mysecret")
            result = await get_current_user(
                basic_credentials=basic_creds,
                bearer_credentials=None,
            )
            assert result == "alice"
            mock_verify.assert_called_once_with("mysecret", "$2b$12$hashedpwd")

    @pytest.mark.asyncio
    async def test_invalid_username(self):
        """Unknown username should raise 401."""
        with patch("src.wes_service.core.security.get_settings") as mock_settings:
            mock_settings.return_value.auth_method = "basic"
            mock_settings.return_value.basic_auth_users = "alice:$2b$12$hashedpwd"

            basic_creds = HTTPBasicCredentials(username="eve", password="pass")
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(
                    basic_credentials=basic_creds,
                    bearer_credentials=None,
                )
            assert exc_info.value.status_code == 401
            assert "Invalid credentials" in exc_info.value.detail

    @pytest.mark.asyncio
    @patch("src.wes_service.core.security.verify_password", return_value=False)
    async def test_invalid_password(self, mock_verify):
        """Wrong password should raise 401."""
        with patch("src.wes_service.core.security.get_settings") as mock_settings:
            mock_settings.return_value.auth_method = "basic"
            mock_settings.return_value.basic_auth_users = "alice:$2b$12$hashedpwd"

            basic_creds = HTTPBasicCredentials(username="alice", password="wrongpass")
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(
                    basic_credentials=basic_creds,
                    bearer_credentials=None,
                )
            assert exc_info.value.status_code == 401
            mock_verify.assert_called_once_with("wrongpass", "$2b$12$hashedpwd")

    @pytest.mark.asyncio
    async def test_no_configured_users_allows_access(self):
        """When no users are configured, any basic credentials should be allowed (dev mode)."""
        with patch("src.wes_service.core.security.get_settings") as mock_settings:
            mock_settings.return_value.auth_method = "basic"
            mock_settings.return_value.basic_auth_users = ""

            basic_creds = HTTPBasicCredentials(username="devuser", password="anything")
            result = await get_current_user(
                basic_credentials=basic_creds,
                bearer_credentials=None,
            )
            assert result == "devuser"

    @pytest.mark.asyncio
    async def test_no_credentials_raises_401(self):
        """No credentials at all should raise 401."""
        with patch("src.wes_service.core.security.get_settings") as mock_settings:
            mock_settings.return_value.auth_method = "basic"

            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(
                    basic_credentials=None,
                    bearer_credentials=None,
                )
            assert exc_info.value.status_code == 401


class TestGetCurrentUserApiToken:
    """Tests for get_current_user with auth_method='api_token'."""

    @pytest.mark.asyncio
    async def test_valid_token_returns_username(self):
        """Valid bearer token should return username from NGS360 API."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"username": "john_doe"}

        with patch("src.wes_service.core.security.get_settings") as mock_settings:
            mock_settings.return_value.auth_method = "api_token"
            mock_settings.return_value.ngs360_api_url = "http://ngs360.example.com"
            mock_settings.return_value.enable_token_cache = True
            mock_settings.return_value.token_cache_max_size = 1000
            mock_settings.return_value.token_cache_ttl_seconds = 300

            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.get.return_value = mock_response
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)
                mock_client_cls.return_value = mock_client

                bearer_creds = HTTPAuthorizationCredentials(
                    scheme="Bearer", credentials="valid-token-123"
                )
                result = await get_current_user(
                    basic_credentials=None,
                    bearer_credentials=bearer_creds,
                )
                assert result == "john_doe"

                # Verify the correct URL and headers were used
                mock_client.get.assert_called_once_with(
                    "http://ngs360.example.com/api/v1/auth/me",
                    headers={
                        "Authorization": "Bearer valid-token-123",
                        "X-Client-Application": "ngs360-ga4gh",
                        "User-Agent": "ngs360-ga4gh/1.0",
                    },
                    timeout=10.0,
                )

    @pytest.mark.asyncio
    async def test_invalid_token_raises_401(self):
        """Invalid bearer token should raise 401."""
        mock_response = MagicMock()
        mock_response.status_code = 401

        with patch("src.wes_service.core.security.get_settings") as mock_settings:
            mock_settings.return_value.auth_method = "api_token"
            mock_settings.return_value.ngs360_api_url = "http://ngs360.example.com"

            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.get.return_value = mock_response
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)
                mock_client_cls.return_value = mock_client

                bearer_creds = HTTPAuthorizationCredentials(
                    scheme="Bearer", credentials="invalid-token"
                )
                with pytest.raises(HTTPException) as exc_info:
                    await get_current_user(
                        basic_credentials=None,
                        bearer_credentials=bearer_creds,
                    )
                assert exc_info.value.status_code == 401
                assert "Invalid or expired" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_auth_service_unavailable_raises_503(self):
        """When NGS360 API is unreachable, should raise 503."""
        import httpx

        with patch("src.wes_service.core.security.get_settings") as mock_settings:
            mock_settings.return_value.auth_method = "api_token"
            mock_settings.return_value.ngs360_api_url = "http://ngs360.example.com"

            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.get.side_effect = httpx.ConnectError("Connection refused")
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)
                mock_client_cls.return_value = mock_client

                bearer_creds = HTTPAuthorizationCredentials(
                    scheme="Bearer", credentials="some-token"
                )
                with pytest.raises(HTTPException) as exc_info:
                    await get_current_user(
                        basic_credentials=None,
                        bearer_credentials=bearer_creds,
                    )
                assert exc_info.value.status_code == 503
                assert "unavailable" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_response_missing_username_raises_401(self):
        """When NGS360 API returns 200 but no username field, should raise 401."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"email": "john@example.com"}  # no "username"

        with patch("src.wes_service.core.security.get_settings") as mock_settings:
            mock_settings.return_value.auth_method = "api_token"
            mock_settings.return_value.ngs360_api_url = "http://ngs360.example.com"

            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.get.return_value = mock_response
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)
                mock_client_cls.return_value = mock_client

                bearer_creds = HTTPAuthorizationCredentials(
                    scheme="Bearer", credentials="token-no-username"
                )
                with pytest.raises(HTTPException) as exc_info:
                    await get_current_user(
                        basic_credentials=None,
                        bearer_credentials=bearer_creds,
                    )
                assert exc_info.value.status_code == 401
                assert "Could not determine username" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_bearer_ignored_when_auth_method_is_basic(self):
        """Bearer token should be ignored if auth_method is 'basic'."""
        with patch("src.wes_service.core.security.get_settings") as mock_settings:
            mock_settings.return_value.auth_method = "basic"
            mock_settings.return_value.basic_auth_users = ""

            # Provide bearer but no basic — should fail since auth_method is basic
            bearer_creds = HTTPAuthorizationCredentials(
                scheme="Bearer", credentials="some-token"
            )
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(
                    basic_credentials=None,
                    bearer_credentials=bearer_creds,
                )
            assert exc_info.value.status_code == 401


class TestValidateApiToken:
    """Tests for validate_api_token directly."""

    @pytest.mark.asyncio
    async def test_successful_validation(self):
        """Successful token validation returns username."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"username": "test_user", "id": 42}

        with patch("src.wes_service.core.security.get_settings") as mock_settings:
            mock_settings.return_value.ngs360_api_url = "http://ngs360.example.com"
            mock_settings.return_value.enable_token_cache = True
            mock_settings.return_value.token_cache_max_size = 1000
            mock_settings.return_value.token_cache_ttl_seconds = 300

            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.get.return_value = mock_response
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)
                mock_client_cls.return_value = mock_client

                result = await validate_api_token("my-valid-token")
                assert result == "test_user"

    @pytest.mark.asyncio
    async def test_expired_token(self):
        """Expired token returns non-200 from API, should raise HTTPException."""
        mock_response = MagicMock()
        mock_response.status_code = 403

        with patch("src.wes_service.core.security.get_settings") as mock_settings:
            mock_settings.return_value.ngs360_api_url = "http://ngs360.example.com"

            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.get.return_value = mock_response
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)
                mock_client_cls.return_value = mock_client

                with pytest.raises(HTTPException) as exc_info:
                    await validate_api_token("expired-token")
                assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_network_timeout(self):
        """Network timeout should raise 503."""
        import httpx

        with patch("src.wes_service.core.security.get_settings") as mock_settings:
            mock_settings.return_value.ngs360_api_url = "http://ngs360.example.com"

            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.get.side_effect = httpx.ReadTimeout("Read timed out")
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)
                mock_client_cls.return_value = mock_client

                with pytest.raises(HTTPException) as exc_info:
                    await validate_api_token("some-token")
                assert exc_info.value.status_code == 503
