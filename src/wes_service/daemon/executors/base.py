"""Base workflow executor interface."""

from abc import ABC, abstractmethod

from sqlalchemy.orm import Session

from src.wes_service.db.models import WorkflowRun


class WorkflowExecutor(ABC):
    """
    Abstract base class for workflow executors.

    Executors are responsible for actually running workflows using
    specific workflow engines (cwltool, Cromwell, Nextflow, etc.).
    """

    @abstractmethod
    def execute(self, db: Session, run: WorkflowRun) -> None:
        """
        Execute a workflow run.

        Args:
            db: Database session for updating run status
            run: WorkflowRun to execute

        The executor should:
        1. Update run state through: INITIALIZING -> RUNNING -> COMPLETE/ERROR
        2. Create TaskLog entries for workflow steps
        3. Handle outputs and store them appropriately
        4. Update timing information (start_time, end_time)
        5. Handle errors and set appropriate error states
        """
