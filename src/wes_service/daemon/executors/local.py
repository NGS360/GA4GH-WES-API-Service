"""Local stub executor for demonstration purposes."""

import asyncio
import logging
from datetime import datetime
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

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

    async def execute(self, db: AsyncSession, run: WorkflowRun) -> None:
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
            run.start_time = datetime.utcnow()
            run.system_logs.append(
                f"Started execution at {run.start_time.isoformat()}"
            )
            await db.commit()

            # Simulate workflow execution
            logger.info(f"Simulating workflow {run.workflow_type} execution...")

            # Create some sample tasks
            task1 = TaskLog(
                id=str(uuid4()),
                run_id=run.id,
                name="Download inputs",
                cmd=["wget", run.workflow_url],
                start_time=datetime.utcnow(),
            )
            db.add(task1)
            await db.commit()

            # Simulate task execution time
            await asyncio.sleep(2)

            task1.end_time = datetime.utcnow()
            task1.exit_code = 0
            await db.commit()

            # Task 2: Process data
            task2 = TaskLog(
                id=str(uuid4()),
                run_id=run.id,
                name="Process workflow",
                cmd=[run.workflow_type.lower(), "run", "workflow.cwl"],
                start_time=datetime.utcnow(),
            )
            db.add(task2)
            await db.commit()

            await asyncio.sleep(3)

            task2.end_time = datetime.utcnow()
            task2.exit_code = 0
            await db.commit()

            # Task 3: Upload outputs
            task3 = TaskLog(
                id=str(uuid4()),
                run_id=run.id,
                name="Upload outputs",
                cmd=["aws", "s3", "cp", "outputs/", "s3://bucket/"],
                start_time=datetime.utcnow(),
            )
            db.add(task3)
            await db.commit()

            await asyncio.sleep(1)

            task3.end_time = datetime.utcnow()
            task3.exit_code = 0
            await db.commit()

            # Complete successfully
            run.state = WorkflowState.COMPLETE
            run.end_time = datetime.utcnow()
            run.exit_code = 0
            run.outputs = {
                "output_file": f"s3://bucket/runs/{run.id}/output.txt",
                "metrics": {"duration_seconds": 6, "tasks_completed": 3},
            }
            run.system_logs.append(
                f"Completed execution at {run.end_time.isoformat()}"
            )

            await db.commit()
            logger.info(f"Successfully completed run {run.id}")

        except Exception as e:
            logger.error(f"Error executing run {run.id}: {e}")

            # Update to error state
            run.state = WorkflowState.EXECUTOR_ERROR
            run.end_time = datetime.utcnow()
            run.exit_code = 1
            run.system_logs.append(f"Execution error: {str(e)}")

            await db.commit()
            raise