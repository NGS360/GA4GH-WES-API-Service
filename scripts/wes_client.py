#!/usr/bin/env python3
"""
WES Client - Python client for GA4GH Workflow Execution Service API.

Example usage:
    # Submit a workflow
    python wes_client.py submit --workflow-url https://example.com/workflow.cwl \
        --workflow-type CWL --workflow-version v1.0

    # List runs
    python wes_client.py list

    # Get run status
    python wes_client.py status <run_id>

    # Cancel run
    python wes_client.py cancel <run_id>
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import httpx


class WESClient:
    """Client for interacting with GA4GH WES API."""

    def __init__(
        self,
        base_url: str = "http://localhost:8000/ga4gh/wes/v1",
        username: str | None = None,
        password: str | None = None,
    ):
        """
        Initialize WES client.

        Args:
            base_url: Base URL of WES service
            username: Username for authentication
            password: Password for authentication
        """
        self.base_url = base_url.rstrip("/")
        self.auth = (username, password) if username and password else None

    def get_service_info(self) -> dict[str, Any]:
        """Get service information."""
        response = httpx.get(f"{self.base_url}/service-info", auth=self.auth)
        response.raise_for_status()
        return response.json()

    def submit_workflow(
        self,
        workflow_url: str,
        workflow_type: str,
        workflow_type_version: str,
        workflow_params: dict[str, Any] | None = None,
        workflow_attachments: list[Path] | None = None,
        tags: dict[str, str] | None = None,
        workflow_engine: str | None = None,
        workflow_engine_version: str | None = None,
    ) -> str:
        """
        Submit a workflow for execution.

        Args:
            workflow_url: URL to workflow definition
            workflow_type: Workflow type (CWL, WDL)
            workflow_type_version: Workflow type version
            workflow_params: Workflow input parameters
            workflow_attachments: Files to attach
            tags: Workflow tags
            workflow_engine: Workflow engine name
            workflow_engine_version: Workflow engine version

        Returns:
            Run ID
        """
        files = {}
        data = {
            "workflow_url": workflow_url,
            "workflow_type": workflow_type,
            "workflow_type_version": workflow_type_version,
        }

        if workflow_params:
            data["workflow_params"] = json.dumps(workflow_params)

        if tags:
            data["tags"] = json.dumps(tags)

        if workflow_engine:
            data["workflow_engine"] = workflow_engine

        if workflow_engine_version:
            data["workflow_engine_version"] = workflow_engine_version

        if workflow_attachments:
            files["workflow_attachment"] = [
                ("workflow_attachment", (f.name, open(f, "rb")))
                for f in workflow_attachments
            ]

        response = httpx.post(
            f"{self.base_url}/runs",
            data=data,
            files=files if files else None,
            auth=self.auth,
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()["run_id"]

    def list_runs(
        self,
        page_size: int | None = None,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        """List workflow runs."""
        params = {}
        if page_size:
            params["page_size"] = page_size
        if page_token:
            params["page_token"] = page_token

        response = httpx.get(
            f"{self.base_url}/runs",
            params=params,
            auth=self.auth,
        )
        response.raise_for_status()
        return response.json()

    def get_run_status(self, run_id: str) -> dict[str, Any]:
        """Get workflow run status."""
        response = httpx.get(
            f"{self.base_url}/runs/{run_id}/status",
            auth=self.auth,
        )
        response.raise_for_status()
        return response.json()

    def get_run_log(self, run_id: str) -> dict[str, Any]:
        """Get detailed workflow run log."""
        response = httpx.get(
            f"{self.base_url}/runs/{run_id}",
            auth=self.auth,
        )
        response.raise_for_status()
        return response.json()

    def cancel_run(self, run_id: str) -> str:
        """Cancel a workflow run."""
        response = httpx.post(
            f"{self.base_url}/runs/{run_id}/cancel",
            auth=self.auth,
        )
        response.raise_for_status()
        return response.json()["run_id"]

    def list_tasks(
        self,
        run_id: str,
        page_size: int | None = None,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        """List tasks for a workflow run."""
        params = {}
        if page_size:
            params["page_size"] = page_size
        if page_token:
            params["page_token"] = page_token

        response = httpx.get(
            f"{self.base_url}/runs/{run_id}/tasks",
            params=params,
            auth=self.auth,
        )
        response.raise_for_status()
        return response.json()


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="WES API Client")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000/ga4gh/wes/v1",
        help="WES service base URL",
    )
    parser.add_argument("--username", help="Username for authentication")
    parser.add_argument("--password", help="Password for authentication")

    subparsers = parser.add_subparsers(dest="command", help="Command")

    # Service info command
    subparsers.add_parser("info", help="Get service information")

    # Submit command
    submit_parser = subparsers.add_parser("submit", help="Submit workflow")
    submit_parser.add_argument(
        "--workflow-url",
        required=True,
        help="Workflow URL",
    )
    submit_parser.add_argument(
        "--workflow-type",
        required=True,
        choices=["CWL", "WDL"],
        help="Workflow type",
    )
    submit_parser.add_argument(
        "--workflow-version",
        required=True,
        help="Workflow type version",
    )
    submit_parser.add_argument(
        "--workflow-params",
        help="Workflow parameters (JSON string)",
    )
    submit_parser.add_argument(
        "--workflow-params-file",
        type=Path,
        help="Workflow parameters file (JSON)",
    )
    submit_parser.add_argument(
        "--attachments",
        nargs="+",
        type=Path,
        help="Files to attach",
    )

    # List command
    list_parser = subparsers.add_parser("list", help="List workflow runs")
    list_parser.add_argument("--page-size", type=int, help="Page size")

    # Status command
    status_parser = subparsers.add_parser("status", help="Get run status")
    status_parser.add_argument("run_id", help="Run ID")

    # Log command
    log_parser = subparsers.add_parser("log", help="Get run log")
    log_parser.add_argument("run_id", help="Run ID")

    # Cancel command
    cancel_parser = subparsers.add_parser("cancel", help="Cancel run")
    cancel_parser.add_argument("run_id", help="Run ID")

    # Tasks command
    tasks_parser = subparsers.add_parser("tasks", help="List run tasks")
    tasks_parser.add_argument("run_id", help="Run ID")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    client = WESClient(
        base_url=args.base_url,
        username=args.username,
        password=args.password,
    )

    try:
        if args.command == "info":
            result = client.get_service_info()
            print(json.dumps(result, indent=2))

        elif args.command == "submit":
            workflow_params = None
            if args.workflow_params:
                workflow_params = json.loads(args.workflow_params)
            elif args.workflow_params_file:
                workflow_params = json.loads(args.workflow_params_file.read_text())

            run_id = client.submit_workflow(
                workflow_url=args.workflow_url,
                workflow_type=args.workflow_type,
                workflow_type_version=args.workflow_version,
                workflow_params=workflow_params,
                workflow_attachments=args.attachments,
            )
            print(f"Submitted workflow run: {run_id}")

        elif args.command == "list":
            result = client.list_runs(page_size=args.page_size)
            print(json.dumps(result, indent=2))

        elif args.command == "status":
            result = client.get_run_status(args.run_id)
            print(json.dumps(result, indent=2))

        elif args.command == "log":
            result = client.get_run_log(args.run_id)
            print(json.dumps(result, indent=2))

        elif args.command == "cancel":
            run_id = client.cancel_run(args.run_id)
            print(f"Canceled workflow run: {run_id}")

        elif args.command == "tasks":
            result = client.list_tasks(args.run_id)
            print(json.dumps(result, indent=2))

    except httpx.HTTPStatusError as e:
        print(f"HTTP error: {e.response.status_code}", file=sys.stderr)
        print(e.response.text, file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
