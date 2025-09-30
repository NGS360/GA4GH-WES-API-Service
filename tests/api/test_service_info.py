"""Tests for service info endpoint."""

import pytest
from fastapi.testclient import TestClient


def test_get_service_info(client: TestClient):
    """Test getting service information."""
    response = client.get("/ga4gh/wes/v1/service-info")
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == "org.ga4gh.wes"
    assert data["name"] == "Test WES Service"
    assert "workflow_type_versions" in data
    assert "supported_wes_versions" in data
    assert "CWL" in data["workflow_type_versions"]
    assert "WDL" in data["workflow_type_versions"]


def test_service_info_has_required_fields(client: TestClient):
    """Test that service info has all required fields."""
    response = client.get("/ga4gh/wes/v1/service-info")
    data = response.json()

    required_fields = [
        "id",
        "name",
        "type",
        "organization",
        "version",
        "workflow_type_versions",
        "supported_wes_versions",
        "supported_filesystem_protocols",
        "workflow_engine_versions",
        "system_state_counts",
        "auth_instructions_url",
    ]

    for field in required_fields:
        assert field in data, f"Missing required field: {field}"


def test_service_info_workflow_types(client: TestClient):
    """Test workflow type versions in service info."""
    response = client.get("/ga4gh/wes/v1/service-info")
    data = response.json()

    wf_types = data["workflow_type_versions"]
    assert "CWL" in wf_types
    assert "WDL" in wf_types

    # Check CWL versions
    assert "workflow_type_version" in wf_types["CWL"]
    assert isinstance(wf_types["CWL"]["workflow_type_version"], list)
    assert len(wf_types["CWL"]["workflow_type_version"]) > 0


def test_service_info_state_counts(client: TestClient):
    """Test system state counts are present."""
    response = client.get("/ga4gh/wes/v1/service-info")
    data = response.json()

    state_counts = data["system_state_counts"]
    assert isinstance(state_counts, dict)

    # All states should be present
    expected_states = [
        "UNKNOWN",
        "QUEUED",
        "INITIALIZING",
        "RUNNING",
        "PAUSED",
        "COMPLETE",
        "EXECUTOR_ERROR",
        "SYSTEM_ERROR",
        "CANCELED",
        "CANCELING",
        "PREEMPTED",
    ]

    for state in expected_states:
        assert state in state_counts