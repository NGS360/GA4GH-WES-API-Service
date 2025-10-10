"""Tests for storage backends."""

import io
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.wes_service.core.storage import (
    LocalStorageBackend,
    S3StorageBackend,
    get_storage_backend,
)


class TestLocalStorageBackend:
    """Tests for LocalStorageBackend."""

    def test_init(self, tmp_path):
        """Test initialization."""
        storage = LocalStorageBackend(str(tmp_path))
        assert storage.base_path == tmp_path

    @pytest.mark.asyncio
    async def test_upload_file(self, tmp_path):
        """Test uploading a file."""
        storage = LocalStorageBackend(str(tmp_path))

        # Create mock upload file
        mock_file = MagicMock()
        mock_file.read = AsyncMock(return_value=b"test content")

        result = await storage.upload_file(mock_file, "test/file.txt")

        assert result == "test/file.txt"
        file_path = tmp_path / "test" / "file.txt"
        assert file_path.exists()

    @pytest.mark.asyncio
    async def test_download_file(self, tmp_path):
        """Test downloading a file."""
        storage = LocalStorageBackend(str(tmp_path))

        # Create test file
        test_file = tmp_path / "download.txt"
        test_file.write_bytes(b"download content")

        content = await storage.download_file("download.txt")
        assert content == b"download content"

    @pytest.mark.asyncio
    async def test_download_file_not_found(self, tmp_path):
        """Test downloading non-existent file."""
        storage = LocalStorageBackend(str(tmp_path))

        with pytest.raises(FileNotFoundError):
            await storage.download_file("nonexistent.txt")

    @pytest.mark.asyncio
    async def test_get_url(self, tmp_path):
        """Test getting file URL."""
        storage = LocalStorageBackend(str(tmp_path))

        url = await storage.get_url("test/file.txt")
        assert url.startswith("file://")
        assert "test/file.txt" in url

    @pytest.mark.asyncio
    async def test_delete_file(self, tmp_path):
        """Test deleting a file."""
        storage = LocalStorageBackend(str(tmp_path))

        # Create test file
        test_file = tmp_path / "delete.txt"
        test_file.write_bytes(b"content")

        result = await storage.delete_file("delete.txt")
        assert result is True
        assert not test_file.exists()

    @pytest.mark.asyncio
    async def test_file_exists(self, tmp_path):
        """Test checking if file exists."""
        storage = LocalStorageBackend(str(tmp_path))

        # Create test file
        test_file = tmp_path / "exists.txt"
        test_file.write_bytes(b"content")

        assert await storage.file_exists("exists.txt") is True
        assert await storage.file_exists("nonexistent.txt") is False

    @pytest.mark.asyncio
    async def test_path_traversal_protection(self, tmp_path):
        """Test that path traversal attacks are prevented."""
        storage = LocalStorageBackend(str(tmp_path))

        with pytest.raises(ValueError):
            await storage.file_exists("../../../etc/passwd")


class TestS3StorageBackend:
    """Tests for S3StorageBackend."""

    @patch("src.wes_service.core.storage.boto3")
    def test_init(self, mock_boto3):
        """Test initialization."""
        storage = S3StorageBackend(
            bucket_name="test-bucket",
            region="us-east-1",
        )
        assert storage.bucket_name == "test-bucket"
        assert storage.region == "us-east-1"

    @patch("src.wes_service.core.storage.boto3")
    @pytest.mark.asyncio
    async def test_upload_file(self, mock_boto3):
        """Test uploading file to S3."""
        storage = S3StorageBackend(
            bucket_name="test-bucket",
            region="us-east-1",
        )

        mock_file = MagicMock()
        mock_file.read = AsyncMock(return_value=b"test content")
        mock_file.content_type = "text/plain"

        result = await storage.upload_file(mock_file, "test/file.txt")
        assert result == "test/file.txt"

    @patch("src.wes_service.core.storage.boto3")
    @pytest.mark.asyncio
    async def test_get_url(self, mock_boto3):
        """Test getting S3 URL."""
        storage = S3StorageBackend(
            bucket_name="test-bucket",
            region="us-east-1",
        )

        url = await storage.get_url("test/file.txt")
        assert url == "s3://test-bucket/test/file.txt"


class TestGetStorageBackend:
    """Tests for storage backend factory."""

    def test_get_local_storage(self, test_settings):
        """Test getting local storage backend."""
        test_settings.storage_backend = "local"
        test_settings.local_storage_path = "/tmp/test"

        with patch(
            "src.wes_service.core.storage.get_settings",
            return_value=test_settings,
        ):
            storage = get_storage_backend()
            assert isinstance(storage, LocalStorageBackend)

    def test_get_s3_storage(self, test_settings):
        """Test getting S3 storage backend."""
        test_settings.storage_backend = "s3"
        test_settings.s3_bucket_name = "test-bucket"

        with patch(
            "src.wes_service.core.storage.get_settings",
            return_value=test_settings,
        ):
            with patch("src.wes_service.core.storage.boto3"):
                storage = get_storage_backend()
                assert isinstance(storage, S3StorageBackend)

    def test_get_invalid_backend(self, test_settings):
        """Test getting invalid backend."""
        test_settings.storage_backend = "invalid"

        with patch(
            "src.wes_service.core.storage.get_settings",
            return_value=test_settings,
        ):
            with pytest.raises(ValueError):
                get_storage_backend()