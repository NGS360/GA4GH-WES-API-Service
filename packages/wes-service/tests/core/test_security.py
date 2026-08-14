"""Tests for security utilities."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from fastapi import HTTPException
from fastapi.security import HTTPBasicCredentials, HTTPAuthorizationCredentials

from wes_service.core.security import (
    SERVICE_CALLER_IDENTITY,
    get_current_user,
    resolve_service_caller,
    validate_api_token,
    verify_password,
    get_password_hash,
    parse_basic_auth_users,
)


class TestVerifyPassword:
    """Tests for password verification."""

    @patch("wes_service.core.security.pwd_context")
    def test_verify_correct_password(self, mock_ctx):
        """Correct password should verify successfully."""
        mock_ctx.verify.return_value = True
        assert verify_password("mysecret", "$2b$12$fakehash") is True
        mock_ctx.verify.assert_called_once_with("mysecret", "$2b$12$fakehash")

    @patch("wes_service.core.security.pwd_context")
    def test_verify_wrong_password(self, mock_ctx):
        """Wrong password should fail verification."""
        mock_ctx.verify.return_value = False
        assert verify_password("wrongpassword", "$2b$12$fakehash") is False
        mock_ctx.verify.assert_called_once_with("wrongpassword", "$2b$12$fakehash")


class TestGetPasswordHash:
    """Tests for password hashing."""

    @patch("wes_service.core.security.pwd_context")
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
        with patch("wes_service.core.security.get_settings") as mock_settings:
            mock_settings.return_value.basic_auth_users = ""
            users = parse_basic_auth_users()
            assert users == {}

    def test_single_user(self):
        """Single user entry should be parsed correctly."""
        with patch("wes_service.core.security.get_settings") as mock_settings:
            mock_settings.return_value.basic_auth_users = "alice:$2b$12$somehash"
            users = parse_basic_auth_users()
            assert "alice" in users
            assert users["alice"] == "$2b$12$somehash"

    def test_multiple_users(self):
        """Multiple user entries should be parsed correctly."""
        with patch("wes_service.core.security.get_settings") as mock_settings:
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
        with patch("wes_service.core.security.get_settings") as mock_settings:
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
        with patch("wes_service.core.security.get_settings") as mock_settings:
            mock_settings.return_value.auth_method = "none"

            result = await get_current_user(
                basic_credentials=None,
                bearer_credentials=None,
            )
            assert result == "anonymous"

    @pytest.mark.asyncio
    async def test_returns_anonymous_even_with_credentials(self):
        """When auth_method is 'none', should return 'anonymous' even if credentials provided."""
        with patch("wes_service.core.security.get_settings") as mock_settings:
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
    @patch("wes_service.core.security.verify_password", return_value=True)
    async def test_valid_basic_credentials(self, mock_verify):
        """Valid basic credentials should return username."""
        with patch("wes_service.core.security.get_settings") as mock_settings:
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
        with patch("wes_service.core.security.get_settings") as mock_settings:
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
    @patch("wes_service.core.security.verify_password", return_value=False)
    async def test_invalid_password(self, mock_verify):
        """Wrong password should raise 401."""
        with patch("wes_service.core.security.get_settings") as mock_settings:
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
        with patch("wes_service.core.security.get_settings") as mock_settings:
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
        with patch("wes_service.core.security.get_settings") as mock_settings:
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

        with patch("wes_service.core.security.get_settings") as mock_settings:
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

        with patch("wes_service.core.security.get_settings") as mock_settings:
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

        with patch("wes_service.core.security.get_settings") as mock_settings:
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

        with patch("wes_service.core.security.get_settings") as mock_settings:
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
        with patch("wes_service.core.security.get_settings") as mock_settings:
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

        with patch("wes_service.core.security.get_settings") as mock_settings:
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

        with patch("wes_service.core.security.get_settings") as mock_settings:
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

        with patch("wes_service.core.security.get_settings") as mock_settings:
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


class TestResolveServiceCaller:
    """Tests for trusted service-to-service authentication."""

    @staticmethod
    def _settings(mock_settings, *, enabled=True, key="s3cret-service-key"):
        mock_settings.return_value.enable_service_auth = enabled
        mock_settings.return_value.INTERNAL_SERVICE_API_KEY = key
        return mock_settings

    def test_valid_key_returns_asserted_identity(self):
        """A valid key plus X-On-Behalf-Of resolves to the asserted username."""
        with patch("wes_service.core.security.get_settings") as mock_settings:
            self._settings(mock_settings)

            assert resolve_service_caller("s3cret-service-key", "alice") == "alice"

    def test_valid_key_without_identity_falls_back_to_service_name(self):
        """A trusted call that names no user is attributed to the service."""
        with patch("wes_service.core.security.get_settings") as mock_settings:
            self._settings(mock_settings)

            assert resolve_service_caller("s3cret-service-key", None) == SERVICE_CALLER_IDENTITY
            assert resolve_service_caller("s3cret-service-key", "   ") == SERVICE_CALLER_IDENTITY

    def test_identity_is_sanitized_and_bounded(self):
        """Asserted identities cannot inject newlines or grow unbounded."""
        with patch("wes_service.core.security.get_settings") as mock_settings:
            self._settings(mock_settings)

            assert resolve_service_caller(
                "s3cret-service-key", "alice\nINFO: forged log line"
            ) == "aliceINFO: forged log line"
            assert len(resolve_service_caller("s3cret-service-key", "x" * 500)) == 128

    def test_wrong_key_is_rejected(self):
        """A present but incorrect key is a 403, never a downgrade to user auth."""
        with patch("wes_service.core.security.get_settings") as mock_settings:
            self._settings(mock_settings)

            with pytest.raises(HTTPException) as exc_info:
                resolve_service_caller("wrong-key", "alice")
            assert exc_info.value.status_code == 403

    def test_disabled_feature_is_rejected_indistinguishably(self):
        """Disabled and wrong-key both return 403 so the state cannot be probed."""
        with patch("wes_service.core.security.get_settings") as mock_settings:
            self._settings(mock_settings, enabled=False)

            with pytest.raises(HTTPException) as exc_info:
                resolve_service_caller("s3cret-service-key", "alice")
            assert exc_info.value.status_code == 403

    def test_unconfigured_key_never_authenticates(self):
        """An unset server key must not let an empty header through."""
        with patch("wes_service.core.security.get_settings") as mock_settings:
            self._settings(mock_settings, key="")

            for presented in ("", "anything"):
                with pytest.raises(HTTPException) as exc_info:
                    resolve_service_caller(presented, "alice")
                assert exc_info.value.status_code == 500


class TestGetCurrentUserServiceKey:
    """Tests for the service-key path through get_current_user."""

    @pytest.mark.asyncio
    async def test_service_key_makes_no_outbound_call(self):
        """The whole point: authenticating a service must not call APIServer."""
        with patch("wes_service.core.security.get_settings") as mock_settings:
            mock_settings.return_value.enable_service_auth = True
            mock_settings.return_value.INTERNAL_SERVICE_API_KEY = "k"
            mock_settings.return_value.auth_method = "api_token"

            with patch("wes_service.core.security.httpx.AsyncClient") as mock_client_cls:
                result = await get_current_user(
                    x_internal_service_key="k",
                    x_on_behalf_of="alice",
                )

            assert result == "alice"
            mock_client_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_service_key_beats_auth_method_none(self):
        """In dev (auth_method=none) the asserted identity still survives."""
        with patch("wes_service.core.security.get_settings") as mock_settings:
            mock_settings.return_value.enable_service_auth = True
            mock_settings.return_value.INTERNAL_SERVICE_API_KEY = "k"
            mock_settings.return_value.auth_method = "none"

            result = await get_current_user(x_internal_service_key="k", x_on_behalf_of="alice")
            assert result == "alice"

    @pytest.mark.asyncio
    async def test_missing_header_falls_through_to_normal_auth(self):
        """Absent service key leaves existing auth behaviour untouched."""
        with patch("wes_service.core.security.get_settings") as mock_settings:
            mock_settings.return_value.auth_method = "none"

            result = await get_current_user(basic_credentials=None, bearer_credentials=None)
            assert result == "anonymous"

    @pytest.mark.asyncio
    async def test_bad_service_key_does_not_fall_through_to_bearer(self):
        """A wrong service key fails even when a valid bearer token accompanies it."""
        with patch("wes_service.core.security.get_settings") as mock_settings:
            mock_settings.return_value.enable_service_auth = True
            mock_settings.return_value.INTERNAL_SERVICE_API_KEY = "k"
            mock_settings.return_value.auth_method = "api_token"

            bearer = HTTPAuthorizationCredentials(scheme="Bearer", credentials="good-token")
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(
                    bearer_credentials=bearer,
                    x_internal_service_key="wrong",
                )
            assert exc_info.value.status_code == 403
