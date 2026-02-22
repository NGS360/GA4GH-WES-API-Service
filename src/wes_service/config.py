"""Configuration management for WES service."""

from functools import lru_cache
from typing import Literal
from pathlib import Path
import json
import os
from dotenv import load_dotenv

from pydantic import Field, field_validator, computed_field, PrivateAttr
from pydantic_settings import BaseSettings, SettingsConfigDict

import boto3
from botocore.exceptions import ClientError

# Load .env file into os.environ so os.getenv() works correctly
# This must happen before Settings class is instantiated
env_path = Path(__file__).parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)


def get_secret(secret_name: str, region_name: str) -> dict | None:
    """
    Retrieve secrets from AWS Secrets Manager

    Args:
        secret_name: Name of the secret in Secrets Manager
        region_name: AWS region where secret is stored

    Returns:
        dict: Parsed secret value or None if secret cannot be retrieved
    """
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )
    try:
        secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
    except ClientError:
        return None
    # Parse and return the secret
    secret = secret_value_response['SecretString'].replace('\n', '')
    return json.loads(
        secret
    )


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Cache for AWS Secrets Manager to avoid multiple API calls
    # Note: Must use PrivateAttr for Pydantic v2 private attributes
    _secret_cache: dict | None = PrivateAttr(default=None)

    def _get_config_value(
        self,
        env_var_name: str,
        default: str | None = None
    ) -> str | None:
        """
        Get configuration value from environment variable or AWS Secrets Manager (with caching).

        Args:
            env_var_name: Environment variable name to check first
            secret_key_name: Key name in AWS Secrets (defaults to env_var_name if not provided)
            default: Default value to return if not found in env or secrets

        Returns:
            Configuration value, or default value if not found
        """
        # 1. Check environment variable first
        env_value = os.getenv(env_var_name)
        if env_value:
            return env_value

        # 2. Try to get from AWS Secrets Manager with caching
        # Use cached secret if available
        if self._secret_cache is None:
            env_secret = os.getenv('ENV_SECRETS')
            if env_secret:
                self._secret_cache = get_secret(env_secret,
                                                os.getenv("AWS_REGION",
                                                          'us-east-1'))
        if self._secret_cache:
            secret_value = self._secret_cache.get(env_var_name)
            if secret_value is not None:
                return secret_value

        # 3. Return default value if provided
        return default

    # Database Configuration
    @computed_field
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        """Build database URI from env or secrets, defaults to mysql+aiomysql"""
        return self._get_config_value(
            "SQLALCHEMY_DATABASE_URI",
            default="mysql+aiomysql://wes_user:wes_password@localhost:3306/wes_db"
        )

    # NGS360 API Endpoint
    ngs360_api_url: str = Field(
        default="http://localhost:8000",
        description="NGS360 API base URL",
    )

    # Storage Configuration
    storage_backend: Literal["local", "s3"] = Field(
        default="local",
        description="Storage backend to use",
    )
    local_storage_path: str = Field(
        default="/var/wes/storage",
        description="Path for local file storage",
    )
    s3_bucket_name: str = Field(
        default="",
        description="S3 bucket name for storage",
    )
    s3_region: str = Field(
        default="us-east-1",
        description="AWS region for S3",
    )
    s3_access_key_id: str = Field(
        default="",
        description="AWS access key ID",
    )
    s3_secret_access_key: str = Field(
        default="",
        description="AWS secret access key",
    )

    # Workflow executor configuration
    workflow_executor: Literal["local", "omics"] = Field(
        default="local",
        description="Workflow executor to use",
    )

    # AWS Omics Configuration
    omics_region: str = Field(
        default="us-east-1",
        description="AWS region for Omics",
    )
    omics_role_arn: str = Field(
        default="",
        description="AWS IAM role ARN for Omics workflow execution",
    )
    omics_output_bucket: str = Field(
        default="s3://omics-outputs",
        description="S3 bucket URI for Omics workflow outputs",
    )

    # Daemon Configuration
    daemon_poll_interval: int = Field(
        default=30,
        description="Interval in seconds between workflow status polling",
    )
    daemon_max_concurrent_runs: int = Field(
        default=10,
        description="Maximum number of concurrent workflow runs",
    )

    # Authentication Configuration
    auth_method: Literal["basic", "oauth2", "none"] = Field(
        default="basic",
        description="Authentication method",
    )
    basic_auth_users: str = Field(
        default="",
        description="Comma-separated list of username:hashed_password pairs",
    )

    # Service Configuration
    service_name: str = Field(
        default="GA4GH WES Service",
        description="Service name",
    )
    service_organization_name: str = Field(
        default="Your Organization",
        description="Organization name",
    )
    service_organization_url: str = Field(
        default="https://example.com",
        description="Organization URL",
    )
    service_environment: str = Field(
        default="development",
        description="Service environment",
    )
    service_version: str = Field(
        default="1.1.0",
        description="Service version",
    )
    service_contact_url: str = Field(
        default="https://example.com/support",
        description="Contact URL",
    )
    service_documentation_url: str = Field(
        default="https://example.com/docs",
        description="Documentation URL",
    )
    auth_instructions_url: str = Field(
        default="https://example.com/auth-help",
        description="URL with authentication instructions",
    )

    # API Configuration
    api_prefix: str = Field(
        default="/ga4gh/wes/v1",
        description="API URL prefix",
    )
    cors_origins: str = Field(
        default="*",
        description="Comma-separated list of allowed CORS origins",
    )
    host: str = Field(
        default="0.0.0.0",
        description="Host to bind to",
    )
    port: int = Field(
        default=8000,
        description="Port to bind to",
    )

    # Logging Configuration
    log_level: str = Field(
        default="INFO",
        description="Logging level",
    )
    log_format: Literal["json", "text"] = Field(
        default="json",
        description="Log output format",
    )

    # Supported Workflow Types
    supported_wes_versions: str = Field(
        default="1.0.0,1.1.0",
        description="Comma-separated list of supported WES versions",
    )
    workflow_type_versions_cwl: str = Field(
        default="v1.0,v1.1,v1.2",
        description="Comma-separated list of supported CWL versions",
    )
    workflow_type_versions_wdl: str = Field(
        default="1.0,draft-2",
        description="Comma-separated list of supported WDL versions",
    )
    workflow_engine_versions_cwltool: str = Field(
        default="3.1.20240116213856",
        description="Comma-separated list of supported cwltool versions",
    )
    supported_filesystem_protocols: str = Field(
        default="file,http,https,s3",
        description="Comma-separated list of supported filesystem protocols",
    )

    # File Upload Limits
    max_upload_size_mb: int = Field(
        default=1024,
        description="Maximum upload size in MB",
    )
    max_attachment_count: int = Field(
        default=100,
        description="Maximum number of attachments per workflow",
    )

    @field_validator("cors_origins")
    @classmethod
    def parse_cors_origins(cls, v: str) -> list[str]:
        """Parse CORS origins from comma-separated string."""
        if v == "*":
            return ["*"]
        return [origin.strip() for origin in v.split(",") if origin.strip()]

    @field_validator("supported_wes_versions")
    @classmethod
    def parse_wes_versions(cls, v: str) -> list[str]:
        """Parse WES versions from comma-separated string."""
        return [version.strip() for version in v.split(",") if version.strip()]

    @field_validator("workflow_type_versions_cwl")
    @classmethod
    def parse_cwl_versions(cls, v: str) -> list[str]:
        """Parse CWL versions from comma-separated string."""
        return [version.strip() for version in v.split(",") if version.strip()]

    @field_validator("workflow_type_versions_wdl")
    @classmethod
    def parse_wdl_versions(cls, v: str) -> list[str]:
        """Parse WDL versions from comma-separated string."""
        return [version.strip() for version in v.split(",") if version.strip()]

    @field_validator("workflow_engine_versions_cwltool")
    @classmethod
    def parse_cwltool_versions(cls, v: str) -> list[str]:
        """Parse cwltool versions from comma-separated string."""
        return [version.strip() for version in v.split(",") if version.strip()]

    @field_validator("supported_filesystem_protocols")
    @classmethod
    def parse_filesystem_protocols(cls, v: str) -> list[str]:
        """Parse filesystem protocols from comma-separated string."""
        return [protocol.strip() for protocol in v.split(",") if protocol.strip()]

    def get_workflow_type_versions(self) -> dict[str, dict[str, list[str]]]:
        """Get workflow type versions in the format expected by ServiceInfo."""
        return {
            "CWL": {"workflow_type_version": self.workflow_type_versions_cwl},
            "WDL": {"workflow_type_version": self.workflow_type_versions_wdl},
        }

    def get_workflow_engine_versions(self) -> dict[str, dict[str, list[str]]]:
        """Get workflow engine versions in the format expected by ServiceInfo."""
        return {
            "cwltool": {"workflow_engine_version": self.workflow_engine_versions_cwltool},
        }

    @property
    def max_upload_size_bytes(self) -> int:
        """Get maximum upload size in bytes."""
        return self.max_upload_size_mb * 1024 * 1024

    # Callback Endpoint Configuration
    enable_callback_endpoint: bool = Field(
        default=True,
        description="Enable internal callback endpoint for event-driven updates",
    )

    @computed_field
    @property
    def INTERNAL_CALLBACK_API_KEY(self) -> str:
        """Get internal callback API key from env or secrets"""
        return self._get_config_value(
            "INTERNAL_CALLBACK_API_KEY",
            default=""
        )

    callback_timeout_seconds: int = Field(
        default=30,
        description="Timeout for callback endpoint processing",
    )

@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


if __name__ == "__main__":
    # To use in other modules
    # from core.config import get_settings
    print(get_settings().SQLALCHEMY_DATABASE_URI)
