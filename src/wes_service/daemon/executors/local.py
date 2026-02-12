"""Local stub executor for demonstration purposes."""

import logging
import time
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from src.wes_service.daemon.executors.base import WorkflowExecutor
from src.wes_service.db.models import TaskLog, WorkflowRun, WorkflowState

logger = logging.getLogger(__name__)


class LocalExecutor(WorkflowExecutor):
    """
    Local stub executor that simulates workflow execution.

    This is a demonstration executor that doesn't actually run workflows.
    In production, this would be replaced with real workflow engine
    integration (cwltool, Cromwell, Nextflow, etc.).
    """

    def execute(self, db: Session, run: WorkflowRun) -> None:
        """
        Simulate workflow execution.

        Args:
            db: Database session
            run: WorkflowRun to execute
        """
        try:
            logger.info(f"Starting execution of run {run.id}")

            # Update to RUNNING
            run.state = WorkflowState.RUNNING
            run.start_time = datetime.now(timezone.utc)
            run.system_logs.append(
                f"Started execution at {run.start_time.isoformat()}"
            )
            db.commit()

            # Simulate workflow execution
            workflow_type = run.workflow_type
            logger.info(f"Simulating workflow {workflow_type} execution...")

            # Create some sample tasks
            task1 = TaskLog(
                id=str(uuid4()),
                run_id=run.id,
                name="Download inputs",
                cmd=["wget", run.workflow_url],
                start_time=datetime.now(timezone.utc),
            )
            db.add(task1)
            db.commit()

            # Simulate task execution time
            time.sleep(2)

            task1.end_time = datetime.now(timezone.utc)
            task1.exit_code = 0
            db.commit()

            # Task 2: Process data
            task2 = TaskLog(
                id=str(uuid4()),
                run_id=run.id,
                name="Process workflow",
                cmd=[run.workflow_type.lower(), "run", "workflow.cwl"],
                start_time=datetime.now(timezone.utc),
            )
            db.add(task2)
            db.commit()

            time.sleep(3)

            task2.end_time = datetime.now(timezone.utc)
            task2.exit_code = 0
            db.commit()

            # Task 3: Upload outputs
            task3 = TaskLog(
                id=str(uuid4()),
                run_id=run.id,
                name="Upload outputs",
                cmd=["aws", "s3", "cp", "outputs/", "s3://bucket/"],
                start_time=datetime.now(timezone.utc),
            )
            db.add(task3)
            db.commit()

            time.sleep(1)

            task3.end_time = datetime.now(timezone.utc)
            task3.exit_code = 0
            db.commit()

            # Complete successfully
            run.state = WorkflowState.COMPLETE
            run.end_time = datetime.now(timezone.utc)
            run.exit_code = 0
            run.outputs = {
                "output_file": f"s3://bucket/runs/{run.id}/output.txt",
                "metrics": {"duration_seconds": 6, "tasks_completed": 3},
            }
            run.system_logs.append(
                f"Completed execution at {run.end_time.isoformat()}"
            )

            db.commit()
            logger.info(f"Successfully completed run {run.id}")

        except Exception as e:
            logger.error(f"Error executing run {run.id}: {e}")

            # Update to error state
            run.state = WorkflowState.EXECUTOR_ERROR
            run.end_time = datetime.now(timezone.utc)
            run.exit_code = 1
            run.system_logs.append(f"Execution error: {str(e)}")

            db.commit()
            raise
