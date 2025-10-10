"""Service info schemas."""

from typing import Any

from pydantic import BaseModel, Field


class WorkflowTypeVersion(BaseModel):
    """Available workflow types supported by the service."""

    workflow_type_version: list[str] = Field(
        ...,
        description="Array of acceptable types for the workflow_type",
    )


class WorkflowEngineVersion(BaseModel):
    """Available workflow engine versions supported by the service."""

    workflow_engine_version: list[str] = Field(
        ...,
        description="Array of acceptable engine versions",
    )


class DefaultWorkflowEngineParameter(BaseModel):
    """Default parameter for a workflow engine."""

    name: str = Field(..., description="The name of the parameter")
    type: str = Field(..., description="The type of the parameter, e.g. float")
    default_value: str = Field(
        ...,
        description="The stringified version of the default parameter",
    )


class ServiceInfo(BaseModel):
    """
    Service information response.

    Extends the GA4GH service-info specification with WES-specific fields.
    """

    # GA4GH Service Info fields
    id: str = Field(..., description="Unique ID of the service")
    name: str = Field(..., description="Name of the service")
    type: dict[str, str] = Field(
        ...,
        description="Service type (group, artifact, version)",
    )
    description: str = Field(..., description="Description of the service")
    organization: dict[str, str] = Field(
        ...,
        description="Organization providing the service",
    )
    contactUrl: str = Field(..., description="URL for contacting the service")
    documentationUrl: str = Field(..., description="URL for service docs")
    createdAt: str = Field(..., description="Service creation timestamp")
    updatedAt: str = Field(..., description="Service update timestamp")
    environment: str = Field(
        ...,
        description="Environment (prod, test, dev, staging)",
    )
    version: str = Field(..., description="Service version")

    # WES-specific fields
    workflow_type_versions: dict[str, WorkflowTypeVersion] = Field(
        ...,
        description="Workflow types and their supported versions",
    )
    supported_wes_versions: list[str] = Field(
        ...,
        description="WES schema versions supported by this service",
    )
    supported_filesystem_protocols: list[str] = Field(
        ...,
        description="Filesystem protocols supported (http, https, s3, etc)",
    )
    workflow_engine_versions: dict[str, WorkflowEngineVersion] = Field(
        ...,
        description="Workflow engines and their supported versions",
    )
    default_workflow_engine_parameters: list[
        DefaultWorkflowEngineParameter
    ] = Field(
        ...,
        description="Default parameters for workflow engines",
    )
    system_state_counts: dict[str, int] = Field(
        ...,
        description="Count of workflows in each state",
    )
    auth_instructions_url: str = Field(
        ...,
        description="URL with authentication instructions",
    )
    tags: dict[str, str] = Field(
        ...,
        description="Additional service metadata",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "org.ga4gh.wes",
                "name": "GA4GH WES Service",
                "type": {
                    "group": "org.ga4gh",
                    "artifact": "wes",
                    "version": "1.1.0",
                },
                "description": "Workflow Execution Service",
                "organization": {
                    "name": "Your Organization",
                    "url": "https://example.com",
                },
                "contactUrl": "https://example.com/support",
                "documentationUrl": "https://example.com/docs",
                "createdAt": "2024-01-01T00:00:00Z",
                "updatedAt": "2024-01-01T00:00:00Z",
                "environment": "production",
                "version": "1.1.0",
                "workflow_type_versions": {
                    "CWL": {"workflow_type_version": ["v1.0", "v1.1", "v1.2"]},
                    "WDL": {"workflow_type_version": ["1.0", "draft-2"]},
                },
                "supported_wes_versions": ["1.0.0", "1.1.0"],
                "supported_filesystem_protocols": ["file", "http", "https", "s3"],
                "workflow_engine_versions": {
                    "cwltool": {"workflow_engine_version": ["3.1.20240116213856"]}
                },
                "default_workflow_engine_parameters": [],
                "system_state_counts": {
                    "QUEUED": 0,
                    "RUNNING": 0,
                    "COMPLETE": 0,
                },
                "auth_instructions_url": "https://example.com/auth",
                "tags": {},
            }
        }
    }