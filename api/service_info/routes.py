from datetime import datetime
from fastapi import APIRouter, Depends

from core.deps import DatabaseSession
from core.config import Settings, get_settings
from api.service_info.models import (
    ServiceInfo, WorkflowTypeVersion, WorkflowEngineVersion
)

router = APIRouter()


@router.get(
    "/service-info",
    response_model=ServiceInfo,
    tags=["Service Info"],
    summary="GetServiceInfo",
    description="Get information about the workflow execution service",
)
def get_service_info(
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
    updated_at = datetime.now(datetime.timezone.utc).isoformat() + "Z"

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
