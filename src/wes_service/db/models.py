"""Database models for WES service."""

import enum
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.wes_service.db.base import Base


class WorkflowState(str, enum.Enum):
    """Workflow execution state enum."""

    UNKNOWN = "UNKNOWN"
    QUEUED = "QUEUED"
    INITIALIZING = "INITIALIZING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETE = "COMPLETE"
    EXECUTOR_ERROR = "EXECUTOR_ERROR"
    SYSTEM_ERROR = "SYSTEM_ERROR"
    CANCELED = "CANCELED"
    CANCELING = "CANCELING"
    PREEMPTED = "PREEMPTED"


class WorkflowRun(Base):
    """Workflow run database model."""

    __tablename__ = "workflow_runs"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    state: Mapped[WorkflowState] = mapped_column(
        Enum(WorkflowState),
        default=WorkflowState.QUEUED,
        nullable=False,
        index=True,
    )

    # Workflow specification
    workflow_type: Mapped[str] = mapped_column(String(50), nullable=False)
    workflow_type_version: Mapped[str] = mapped_column(String(50), nullable=False)
    workflow_url: Mapped[str] = mapped_column(Text, nullable=False)
    workflow_params: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=True,
        default=dict,
    )
    workflow_engine: Mapped[str | None] = mapped_column(String(50), nullable=True)
    workflow_engine_version: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    workflow_engine_parameters: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    tags: Mapped[dict[str, str]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )

    # Execution details
    start_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    end_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Logging
    stdout_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    stderr_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    system_logs: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )

    # Outputs
    outputs: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # User tracking
    user_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # Relationships
    task_logs: Mapped[list["TaskLog"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
    )
    attachments: Mapped[list["WorkflowAttachment"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        """String representation."""
        return f"<WorkflowRun(id={self.id}, state={self.state})>"


class TaskLog(Base):
    """Task log database model."""

    __tablename__ = "task_logs"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Task details
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    cmd: Mapped[list[str]] = mapped_column(JSON, nullable=True, default=list)

    # Execution timing
    start_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    end_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Logging
    stdout_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    stderr_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    system_logs: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )

    # TES integration (optional)
    tes_uri: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # Relationships
    run: Mapped[WorkflowRun] = relationship(back_populates="task_logs")

    def __repr__(self) -> str:
        """String representation."""
        return f"<TaskLog(id={self.id}, name={self.name}, run_id={self.run_id})>"


class WorkflowAttachment(Base):
    """Workflow attachment database model."""

    __tablename__ = "workflow_attachments"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # File details
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    # Relationships
    run: Mapped[WorkflowRun] = relationship(back_populates="attachments")

    def __repr__(self) -> str:
        """String representation."""
        return f"<WorkflowAttachment(id={self.id}, filename={self.filename})>"
