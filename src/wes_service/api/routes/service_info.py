"""Service info endpoint."""

from datetime import datetime

from fastapi import APIRouter, Depends

from src.wes_service.api.deps import DatabaseSession
from src.wes_service.config import Settings, get_settings
from src.wes_service.schemas.service_info import (
    ServiceInfo,
    WorkflowEngineVersion,
    WorkflowTypeVersion,
)
from src.wes_service.services.run_service import RunService

router = APIRouter()


@router.get(
    "/service-info",
    response_model=ServiceInfo,
    tags=["Service Info"],
    summary="GetServiceInfo",
    description="Get information about the workflow execution service",
)
async def get_service_info(
    db: DatabaseSession,
    settings: Settings = Depends(get_settings),
) -> ServiceInfo:
    """
    Get service information including supported workflow types and versions.

    Returns metadata about the WES service including supported workflow
    types, versions, filesystem protocols, and current system state.
    """

    # Get system state counts
    run_service = RunService(db, None)  # type: ignore
    state_counts = await run_service.get_system_state_counts()

    # Build workflow type versions
    workflow_type_versions = {}
    for wf_type, versions in settings.get_workflow_type_versions().items():
        workflow_type_versions[wf_type] = WorkflowTypeVersion(
            workflow_type_version=versions["workflow_type_version"]
        )

    # Build workflow engine versions
    workflow_engine_versions = {}
    for engine, versions in settings.get_workflow_engine_versions().items():
        workflow_engine_versions[engine] = WorkflowEngineVersion(
            workflow_engine_version=versions["workflow_engine_version"]
        )

    # Service creation/update times (static for now)
    created_at = datetime(2024, 1, 1).isoformat() + "Z"
    updated_at = datetime.utcnow().isoformat() + "Z"

    return ServiceInfo(
        id="org.ga4gh.wes",
        name=settings.service_name,
        type={
            "group": "org.ga4gh",
            "artifact": "wes",
            "version": settings.service_version,
        },
        description="GA4GH Workflow Execution Service",
        organization={
            "name": settings.service_organization_name,
            "url": settings.service_organization_url,
        },
        contactUrl=settings.service_contact_url,
        documentationUrl=settings.service_documentation_url,
        createdAt=created_at,
        updatedAt=updated_at,
        environment=settings.service_environment,
        version=settings.service_version,
        workflow_type_versions=workflow_type_versions,
        supported_wes_versions=settings.supported_wes_versions,
        supported_filesystem_protocols=settings.supported_filesystem_protocols,
        workflow_engine_versions=workflow_engine_versions,
        default_workflow_engine_parameters=[],
        system_state_counts=state_counts,
        auth_instructions_url=settings.auth_instructions_url,
        tags={},
    )
