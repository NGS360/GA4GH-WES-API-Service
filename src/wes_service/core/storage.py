"""Storage abstraction layer for file handling."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import BinaryIO

import aiofiles
import boto3
from botocore.exceptions import ClientError
from fastapi import UploadFile

from src.wes_service.config import get_settings


class StorageBackend(ABC):
    """Abstract base class for storage backends."""

    @abstractmethod
    async def upload_file(
        self,
        file: UploadFile | BinaryIO,
        path: str,
    ) -> str:
        """
        Upload a file to storage.

        Args:
            file: File to upload
            path: Relative path where file should be stored

        Returns:
            Storage path of uploaded file
        """
        pass

    @abstractmethod
    async def download_file(self, path: str) -> bytes:
        """
        Download a file from storage.

        Args:
            path: Relative path of file to download

        Returns:
            File contents as bytes
        """
        pass

    @abstractmethod
    async def get_url(self, path: str) -> str:
        """
        Get a URL to access the file.

        Args:
            path: Relative path of file

        Returns:
            URL to access the file
        """
        pass

    @abstractmethod
    async def delete_file(self, path: str) -> bool:
        """
        Delete a file from storage.

        Args:
            path: Relative path of file to delete

        Returns:
            True if file was deleted, False otherwise
        """
        pass

    @abstractmethod
    async def file_exists(self, path: str) -> bool:
        """
        Check if a file exists in storage.

        Args:
            path: Relative path of file

        Returns:
            True if file exists, False otherwise
        """
        pass


class LocalStorageBackend(StorageBackend):
    """Local filesystem storage backend."""

    def __init__(self, base_path: str):
        """
        Initialize local storage backend.

        Args:
            base_path: Base directory for file storage
        """
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _get_full_path(self, path: str) -> Path:
        """Get full filesystem path from relative path."""
        full_path = (self.base_path / path).resolve()
        # Security: Ensure path is within base_path
        if not str(full_path).startswith(str(self.base_path.resolve())):
            raise ValueError(f"Invalid path: {path}")
        return full_path

    async def upload_file(
        self,
        file: UploadFile | BinaryIO,
        path: str,
    ) -> str:
        """Upload file to local filesystem."""
        full_path = self._get_full_path(path)
        full_path.parent.mkdir(parents=True, exist_ok=True)

        if isinstance(file, UploadFile):
            # FastAPI UploadFile
            async with aiofiles.open(full_path, "wb") as f:
                content = await file.read()
                await f.write(content)
        else:
            # Regular file object
            async with aiofiles.open(full_path, "wb") as f:
                content = await file.read()
                await f.write(content)

        return path

    async def download_file(self, path: str) -> bytes:
        """Download file from local filesystem."""
        full_path = self._get_full_path(path)
        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        async with aiofiles.open(full_path, "rb") as f:
            return await f.read()

    async def get_url(self, path: str) -> str:
        """Get file:// URL for local file."""
        full_path = self._get_full_path(path)
        return f"file://{full_path}"

    async def delete_file(self, path: str) -> bool:
        """Delete file from local filesystem."""
        try:
            full_path = self._get_full_path(path)
            if full_path.exists():
                full_path.unlink()
                return True
            return False
        except Exception:
            return False

    async def file_exists(self, path: str) -> bool:
        """Check if file exists in local filesystem."""
        full_path = self._get_full_path(path)
        return full_path.exists()


class S3StorageBackend(StorageBackend):
    """AWS S3 storage backend."""

    def __init__(
        self,
        bucket_name: str,
        region: str,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
    ):
        """
        Initialize S3 storage backend.

        Args:
            bucket_name: S3 bucket name
            region: AWS region
            access_key_id: AWS access key ID (optional, uses env/instance role)
            secret_access_key: AWS secret access key (optional)
        """
        self.bucket_name = bucket_name
        self.region = region

        # Initialize S3 client
        session_kwargs = {"region_name": region}
        if access_key_id and secret_access_key:
            session_kwargs["aws_access_key_id"] = access_key_id
            session_kwargs["aws_secret_access_key"] = secret_access_key

        self.s3_client = boto3.client("s3", **session_kwargs)

    async def upload_file(
        self,
        file: UploadFile | BinaryIO,
        path: str,
    ) -> str:
        """Upload file to S3."""
        try:
            if isinstance(file, UploadFile):
                content = await file.read()
                self.s3_client.put_object(
                    Bucket=self.bucket_name,
                    Key=path,
                    Body=content,
                    ContentType=file.content_type or "application/octet-stream",
                )
            else:
                content = file.read()
                self.s3_client.put_object(
                    Bucket=self.bucket_name,
                    Key=path,
                    Body=content,
                )
            return path
        except ClientError as e:
            raise RuntimeError(f"Failed to upload to S3: {e}")

    async def download_file(self, path: str) -> bytes:
        """Download file from S3."""
        try:
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=path,
            )
            return response["Body"].read()
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                raise FileNotFoundError(f"File not found in S3: {path}")
            raise RuntimeError(f"Failed to download from S3: {e}")

    async def get_url(self, path: str) -> str:
        """Get S3 URL for file."""
        return f"s3://{self.bucket_name}/{path}"

    async def delete_file(self, path: str) -> bool:
        """Delete file from S3."""
        try:
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=path,
            )
            return True
        except ClientError:
            return False

    async def file_exists(self, path: str) -> bool:
        """Check if file exists in S3."""
        try:
            self.s3_client.head_object(
                Bucket=self.bucket_name,
                Key=path,
            )
            return True
        except ClientError:
            return False


def get_storage_backend() -> StorageBackend:
    """
    Get the configured storage backend.

    Returns:
        Configured StorageBackend instance
    """
    settings = get_settings()

    if settings.storage_backend == "local":
        return LocalStorageBackend(settings.local_storage_path)
    elif settings.storage_backend == "s3":
        if not settings.s3_bucket_name:
            raise ValueError("S3_BUCKET_NAME must be set for S3 storage")
        return S3StorageBackend(
            bucket_name=settings.s3_bucket_name,
            region=settings.s3_region,
            access_key_id=settings.s3_access_key_id or None,
            secret_access_key=settings.s3_secret_access_key or None,
        )
    else:
        raise ValueError(f"Unknown storage backend: {settings.storage_backend}")
