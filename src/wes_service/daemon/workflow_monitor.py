"""Workflow monitoring daemon."""

import asyncio
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.wes_service.config import get_settings
from src.wes_service.db.models import WorkflowRun, WorkflowState
from src.wes_service.db.session import AsyncSessionLocal
from src.wes_service.daemon.executors.local import LocalExecutor
from src.wes_service.daemon.executors.omics import OmicsExecutor

logger = logging.getLogger(__name__)


class WorkflowMonitor:
    """
    Daemon that monitors and executes workflow runs.

    This is a stub implementation that demonstrates the architecture.
    In production, this would integrate with actual workflow engines
    like cwltool, Cromwell, or Nextflow.
    """

    def __init__(self):
        """Initialize workflow monitor."""
        self.settings = get_settings()

        # Choose executor based on configuration
        if self.settings.workflow_executor == "omics":
            self.executor = OmicsExecutor()
        else:
            # Default to local executor
            self.executor = LocalExecutor()

        self.running = False
        self.active_runs: set[str] = set()

    async def start(self) -> None:
        """Start the workflow monitor daemon."""
        logger.info("Starting workflow monitor daemon...")
        self.running = True

        try:
            while self.running:
                await self._poll_and_execute()
                await asyncio.sleep(self.settings.daemon_poll_interval)
        except Exception as e:
            logger.error(f"Workflow monitor error: {e}")
            raise
        finally:
            logger.info("Workflow monitor stopped")

    async def stop(self) -> None:
        """Stop the workflow monitor daemon."""
        logger.info("Stopping workflow monitor...")
        self.running = False

    async def _poll_and_execute(self) -> None:
        """Poll for queued workflows and execute them."""
        async with AsyncSessionLocal() as db:
            # Find QUEUED workflows
            query = (
                select(WorkflowRun)
                .where(WorkflowRun.state == WorkflowState.QUEUED)
                .limit(self.settings.daemon_max_concurrent_runs - len(self.active_runs))
            )

            result = await db.execute(query)
            queued_runs = result.scalars().all()

            for run in queued_runs:
                if run.id not in self.active_runs:
                    # Start execution in background
                    asyncio.create_task(self._execute_run(run.id))
                    self.active_runs.add(run.id)

            # Check for CANCELING workflows
            query = select(WorkflowRun).where(
                WorkflowRun.state == WorkflowState.CANCELING
            )
            result = await db.execute(query)
            canceling_runs = result.scalars().all()

            for run in canceling_runs:
                await self._cancel_run(db, run)

    async def _execute_run(self, run_id: str) -> None:
        """
        Execute a workflow run.

        Args:
            run_id: Run ID to execute
        """
        try:
            async with AsyncSessionLocal() as db:
                # Get run
                result = await db.execute(
                    select(WorkflowRun).where(WorkflowRun.id == run_id)
                )
                run = result.scalar_one_or_none()

                if not run:
                    logger.error(f"Run {run_id} not found")
                    return

                logger.info(f"Executing run {run_id}")

                # Update state to INITIALIZING
                run.state = WorkflowState.INITIALIZING
                await db.commit()

                # Execute workflow
                await self.executor.execute(db, run)

        except Exception as e:
            logger.error(f"Error executing run {run_id}: {e}")
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(WorkflowRun).where(WorkflowRun.id == run_id)
                )
                run = result.scalar_one_or_none()
                if run:
                    run.state = WorkflowState.SYSTEM_ERROR
                    run.end_time = datetime.utcnow()
                    run.system_logs.append(f"System error: {str(e)}")
                    await db.commit()
        finally:
            self.active_runs.discard(run_id)

    async def _cancel_run(self, db: AsyncSession, run: WorkflowRun) -> None:
        """
        Cancel a workflow run.

        Args:
            db: Database session
            run: WorkflowRun to cancel
        """
        logger.info(f"Canceling run {run.id}")

        # Update state to CANCELED
        run.state = WorkflowState.CANCELED
        run.end_time = datetime.utcnow()
        run.system_logs.append("Workflow canceled by user")

        await db.commit()
        self.active_runs.discard(run.id)


async def main() -> None:
    """Main entry point for daemon."""
    monitor = WorkflowMonitor()
    try:
        await monitor.start()
    except KeyboardInterrupt:
        await monitor.stop()


if __name__ == "__main__":
    # Configure more detailed logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Increase boto3/botocore logging level to reduce noise
    logging.getLogger('botocore').setLevel(logging.WARNING)
    logging.getLogger('boto3').setLevel(logging.WARNING)

    # Set our application loggers to INFO
    logging.getLogger('src.wes_service').setLevel(logging.INFO)

    logger.info("Starting WES workflow monitor daemon...")

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Workflow monitor stopped by user")
    except Exception as e:
        logger.error(f"Unhandled exception in workflow monitor: {str(e)}", exc_info=True)
