"""Database models for WES service."""

import enum
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from wes_service.db.base import Base


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
    __table_args__ = (
        # Listings are always "one project, newest first". Indexing project
        # alone is worse than no index at all here: it tempts the optimizer off
        # created_at and into a filesort over thousands of wide JSON rows, which
        # exhausts sort_buffer_size on deep pages.
        Index("ix_workflow_runs_project_created_at", "project", "created_at"),
        # Child listings are "one parent, newest first" -- the same access shape,
        # and the same reason for indexing the pair rather than parent_run_id
        # alone. A launcher fans out to hundreds of children in one project, so
        # this is the index that keeps its progress rollup cheap.
        Index("ix_workflow_runs_parent_created_at", "parent_run_id", "created_at"),
    )

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
    project: Mapped[str] = mapped_column(String(50), nullable=False)
    task_name: Mapped[str] = mapped_column(String(200), nullable=False)
    parent_run_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("workflow_runs.id", ondelete="SET NULL"),
        nullable=True,
        comment="Launcher run that submitted this run, if any",
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
    workflow_run_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        index=True,
        comment="ID for executed workflow run in underlying execution system (e.g. Omics Run ID)",
    )
    outputs: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # User tracking
    user_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
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
    # Launcher lineage. No cascade: a launcher run being deleted must not take
    # the child workflows it submitted with it -- they are independent
    # executions whose outputs outlive the orchestration that started them.
    parent: Mapped["WorkflowRun | None"] = relationship(
        back_populates="children",
        remote_side=[id],
    )
    children: Mapped[list["WorkflowRun"]] = relationship(back_populates="parent")

    # Callback tracking
    last_callback_time: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        index=True,
        comment="Last time a callback updated this run",
    )
    last_event_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        comment="Last EventBridge event ID processed (for idempotency)",
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
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
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
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    run: Mapped[WorkflowRun] = relationship(back_populates="attachments")

    def __repr__(self) -> str:
        """String representation."""
        return f"<WorkflowAttachment(id={self.id}, filename={self.filename})>"
