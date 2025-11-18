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

            # Check for existing RUNNING or INITIALIZING workflows that might have been
            # submitted before the daemon was started
            if not hasattr(self, '_checked_existing_runs'):
                await self._check_existing_runs(db)
                self._checked_existing_runs = True

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
            # Create a new session for error handling to avoid transaction conflicts
            async with AsyncSessionLocal() as error_db:
                result = await error_db.execute(
                    select(WorkflowRun).where(WorkflowRun.id == run_id)
                )
                error_run = result.scalar_one_or_none()
                if error_run:
                    error_run.state = WorkflowState.SYSTEM_ERROR
                    error_run.end_time = datetime.utcnow()
                    error_run.system_logs.append(f"System error: {str(e)}")
                    await error_db.commit()
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

    async def _check_existing_runs(self, db: AsyncSession) -> None:
        """
        Check for existing runs in RUNNING or INITIALIZING state.

        This is used to monitor runs that were submitted before the daemon was started.

        Args:
            db: Database session
        """
        logger.info("Checking for existing runs in RUNNING or INITIALIZING state...")

        # Find runs in RUNNING or INITIALIZING state
        query = select(WorkflowRun).where(
            (WorkflowRun.state == WorkflowState.RUNNING) |
            (WorkflowRun.state == WorkflowState.INITIALIZING)
        )

        result = await db.execute(query)
        existing_runs = result.scalars().all()

        if existing_runs:
            logger.info(f"Found {len(existing_runs)} existing runs to monitor")

            for run in existing_runs:
                if run.id not in self.active_runs:
                    logger.info(f"Monitoring existing run {run.id} in state {run.state}")

                    # Check if the run has an Omics run ID
                    omics_run_id = None
                    if run.outputs and "omics_run_id" in run.outputs:
                        omics_run_id = run.outputs["omics_run_id"]
                        logger.info(f"Found Omics run ID {omics_run_id} for run {run.id}")

                    if omics_run_id:
                        # Start monitoring the run with a new database session
                        # Don't pass the current db session to avoid transaction conflicts
                        asyncio.create_task(self._monitor_existing_run(run.id, omics_run_id))
                        self.active_runs.add(run.id)
                    else:
                        # No Omics run ID found, mark as CANCELED
                        logger.warning((f"No Omics run ID found for run {run.id}, "
                                        f"marking as CANCELED"))
                        run.state = WorkflowState.CANCELED
                        run.end_time = datetime.utcnow()
                        run.system_logs.append("Run marked as CANCELED: No Omics run ID found")
                        await db.commit()
        else:
            logger.info("No existing runs found to monitor")

    async def _monitor_existing_run(self, run_id: str, omics_run_id: str) -> None:
        """
        Monitor an existing run that was submitted before the daemon was started.

        Args:
            run_id: ID of the WorkflowRun to monitor
            omics_run_id: AWS Omics run ID
        """
        try:
            logger.info(f"Monitoring existing run {run_id} with Omics run ID {omics_run_id}")

            # Create a new database session for this task
            async with AsyncSessionLocal() as db:
                # Get the run from the database
                result = await db.execute(
                    select(WorkflowRun).where(WorkflowRun.id == run_id)
                )
                run = result.scalar_one_or_none()

                if not run:
                    logger.error(f"Run {run_id} not found")
                    self.active_runs.discard(run_id)
                    return

                # Use the executor to monitor the run
                if isinstance(self.executor, OmicsExecutor):
                    # First check if the Omics run exists
                    try:
                        # Try to get the run from Omics
                        omics_run = self.executor.omics_client.get_run(id=omics_run_id)
                        logger.info((f"Found Omics run {omics_run_id} with status "
                                     f"{omics_run.get('status')}"))
                    except Exception as e:
                        # Run not found in Omics, mark as CANCELED
                        logger.warning(f"Omics run {omics_run_id} not found in AWS HealthOmics: {e}")
                        run.state = WorkflowState.CANCELED
                        run.end_time = datetime.utcnow()
                        run.system_logs.append((f"Run marked as CANCELED: Omics run {omics_run_id} "
                                                f"not found in AWS HealthOmics"))
                        run.exit_code = 1
                        await db.commit()
                        self.active_runs.discard(run_id)
                        return

                    # Monitor the run until completion
                    final_state = await self.executor._monitor_omics_run(db, run, omics_run_id)

                    # Update run state based on Omics result
                    run.state = final_state
                    run.end_time = datetime.utcnow()

                    if final_state == WorkflowState.COMPLETE:
                        run.exit_code = 0
                        # Get outputs from Omics
                        try:
                            outputs = self.executor._get_run_outputs(omics_run_id)
                            run.outputs = outputs
                            await db.commit()
                            logger.info(f"Committed outputs to database for run {run.id}")

                            # Update log URLs in the database
                            if 'logs' in outputs:
                                if 'run_log' in outputs['logs']:
                                    # Set the stdout_url directly
                                    run.stdout_url = outputs['logs']['run_log']
                                    logger.info(f"Run {run.id}: Set stdout_url to {run.stdout_url}")

                                # Update task log URLs
                                if 'task_logs' in outputs['logs']:
                                    await self.executor._update_task_log_urls(
                                        db, run.id, outputs['logs']['task_logs']
                                    )

                                    # Create a default task log if none exists
                                    # This ensures we have at least one task log entry in database
                                    task_name = 'main'
                                    log_url = outputs['logs']['task_logs'].get(task_name)
                                    if log_url:
                                        # Check if task exists
                                        from src.wes_service.db.models import TaskLog

                                        query = select(TaskLog).where(
                                            TaskLog.run_id == run.id,
                                            TaskLog.name == task_name
                                        )
                                        result = await db.execute(query)
                                        task = result.scalar_one_or_none()

                                        if not task:
                                            # Create a new task log entry
                                            logger.info((f"Creating default task log "
                                                         f"for run {run.id}"))
                                            task = TaskLog(
                                                id=f"omics-{omics_run_id}-{task_name}",
                                                run_id=run.id,
                                                name=task_name,
                                                cmd=[],
                                                start_time=None,
                                                end_time=datetime.utcnow(),
                                                exit_code=0,
                                                stdout_url=log_url,
                                                system_logs=[f"Task created from log URL: {log_url}"]
                                            )
                                            db.add(task)
                                            await db.commit()
                                            logger.info(f"Created default task log for run {run.id}")

                            run.system_logs.append(f"Workflow completed successfully at "
                                                   f"{run.end_time.isoformat()}")
                            logger.info((f"Run {run.id}: Workflow completed successfully "
                                         f"at {run.end_time.isoformat()}"))
                        except Exception as e:
                            error_msg = (f"Workflow completed but failed to "
                                         f"retrieve outputs: {str(e)}")
                            logger.warning(f"Run {run.id}: {error_msg}")
                            run.system_logs.append(error_msg)
                    else:
                        run.exit_code = 1
                        log_msg = (f"Workflow failed with state {final_state} "
                                   f"at {run.end_time.isoformat()}")
                        run.system_logs.append(log_msg)
                        logger.error(f"Run {run.id}: {log_msg}")

                    # Make sure to commit the changes to the database
                    await db.commit()
                    logger.info(f"Committed state update for run {run.id} to database: {run.state}")
                else:
                    logger.warning((f"Executor is not OmicsExecutor, "
                                    f"cannot monitor existing run {run.id}"))

        except Exception as e:
            logger.error(f"Error monitoring existing run {run_id}: {e}")
            try:
                # Create a new session in case the previous one was closed or in an error state
                async with AsyncSessionLocal() as error_db:
                    # Get the run again to update its state
                    result = await error_db.execute(
                        select(WorkflowRun).where(WorkflowRun.id == run_id)
                    )
                    error_run = result.scalar_one_or_none()
                    if error_run:
                        error_run.state = WorkflowState.SYSTEM_ERROR
                        error_run.end_time = datetime.utcnow()
                        error_run.system_logs.append(
                            f"System error monitoring existing run: {str(e)}"
                        )
                        error_run.exit_code = 1
                        await error_db.commit()
                        logger.info(f"Updated run {run_id} to SYSTEM_ERROR state due to exception")
            except Exception as inner_e:
                logger.error(f"Failed to update error state for run {run_id}: {inner_e}")
        finally:
            self.active_runs.discard(run_id)
            logger.info(f"Removed run {run_id} from active runs")


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
