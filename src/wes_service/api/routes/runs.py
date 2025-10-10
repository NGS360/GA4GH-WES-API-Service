"""Workflow runs endpoints."""

from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile, status

from src.wes_service.api.deps import CurrentUser, DatabaseSession, Storage
from src.wes_service.schemas.run import (
    RunId,
    RunListResponse,
    RunLog,
    RunStatus,
)
from src.wes_service.services.run_service import RunService

router = APIRouter()


@router.get(
    "/runs",
    response_model=RunListResponse,
    tags=["Workflow Runs"],
    summary="ListRuns",
    description="List workflow runs with pagination",
)
async def list_runs(
    db: DatabaseSession,
    user: CurrentUser,
    page_size: int | None = None,
    page_token: str | None = None,
) -> RunListResponse:
    """
    List workflow runs.

    This list is provided in a stable ordering. The client should not
    make assumptions about live updates. Use GetRunStatus or GetRunLog
    to monitor specific runs.
    """
    service = RunService(db, None)  # type: ignore
    return await service.list_runs(page_size, page_token, user)


@router.post(
    "/runs",
    response_model=RunId,
    status_code=status.HTTP_200_OK,
    tags=["Workflow Runs"],
    summary="RunWorkflow",
    description="Submit a new workflow for execution",
)
async def run_workflow(
    db: DatabaseSession,
    storage: Storage,
    user: CurrentUser,
    workflow_params: Annotated[str | None, Form()] = None,
    workflow_type: Annotated[str, Form()] = ...,
    workflow_type_version: Annotated[str, Form()] = ...,
    workflow_url: Annotated[str, Form()] = ...,
    workflow_attachment: Annotated[
        list[UploadFile] | None,
        File(),
    ] = None,
    tags: Annotated[str | None, Form()] = None,
    workflow_engine: Annotated[str | None, Form()] = None,
    workflow_engine_version: Annotated[str | None, Form()] = None,
    workflow_engine_parameters: Annotated[str | None, Form()] = None,
) -> RunId:
    """
    Submit a new workflow run.

    The workflow_attachment array may be used to upload files required
    to execute the workflow. The workflow_url is either an absolute URL
    or a relative URL corresponding to one of the attachments.

    The workflow_params JSON object specifies input parameters.
    The exact format depends on the workflow language conventions.
    """
    service = RunService(db, storage)
    run_id = await service.create_run(
        workflow_params=workflow_params,
        workflow_type=workflow_type,
        workflow_type_version=workflow_type_version,
        workflow_url=workflow_url,
        workflow_attachments=workflow_attachment,
        tags=tags,
        workflow_engine=workflow_engine,
        workflow_engine_version=workflow_engine_version,
        workflow_engine_parameters=workflow_engine_parameters,
        user_id=user,
    )
    return RunId(run_id=run_id)


@router.get(
    "/runs/{run_id}",
    response_model=RunLog,
    tags=["Workflow Runs"],
    summary="GetRunLog",
    description="Get detailed information about a workflow run",
)
async def get_run_log(
    run_id: str,
    db: DatabaseSession,
    user: CurrentUser,
) -> RunLog:
    """
    Get detailed workflow run information.

    Returns information about outputs, logs for stderr/stdout,
    task logs, and overall workflow state.
    """
    service = RunService(db, None)  # type: ignore
    return await service.get_run_log(run_id, user)


@router.get(
    "/runs/{run_id}/status",
    response_model=RunStatus,
    tags=["Workflow Runs"],
    summary="GetRunStatus",
    description="Get abbreviated status of a workflow run",
)
async def get_run_status(
    run_id: str,
    db: DatabaseSession,
    user: CurrentUser,
) -> RunStatus:
    """
    Get workflow run status.

    Provides a fast, abbreviated status check returning only the
    workflow state without detailed logs.
    """
    service = RunService(db, None)  # type: ignore
    return await service.get_run_status(run_id, user)


@router.post(
    "/runs/{run_id}/cancel",
    response_model=RunId,
    tags=["Workflow Runs"],
    summary="CancelRun",
    description="Cancel a running workflow",
)
async def cancel_run(
    run_id: str,
    db: DatabaseSession,
    user: CurrentUser,
) -> RunId:
    """
    Cancel a running workflow.

    Updates the workflow state to CANCELING and then CANCELED.
    Cannot cancel workflows that are already in a terminal state.
    """
    service = RunService(db, None)  # type: ignore
    canceled_id = await service.cancel_run(run_id, user)
    return RunId(run_id=canceled_id)