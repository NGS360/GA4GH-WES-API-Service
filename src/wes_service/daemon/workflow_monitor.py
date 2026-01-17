"""Workflow monitoring daemon."""

# To debug: PYTHONPATH=. python3 -m pudb -m src.wes_service.daemon.workflow_monitor
import json
import logging
from datetime import datetime, timezone
from time import sleep

from sqlalchemy import select
from sqlalchemy.orm import Session, attributes

from src.wes_service.config import get_settings
from src.wes_service.db.models import WorkflowRun, WorkflowState
#from src.wes_service.daemon.executors.local import LocalExecutor
from src.wes_service.daemon.executors.omics import OmicsExecutor

# Create sync engine since we don't need async for the daemon
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

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
            # self.executor = LocalExecutor()
            raise ValueError("Unsupported workflow executor configured")

        self.running = False

        if self.settings.SQLALCHEMY_DATABASE_URI.startswith("mysql+aiomysql"):
            SQLALCHEMY_DATABASE_URI = self.settings.SQLALCHEMY_DATABASE_URI.replace(
                "mysql+aiomysql", "mysql+pymysql"
            )
        # Create GA4GH WES database engine
        self.engine = create_engine(
            SQLALCHEMY_DATABASE_URI,
            echo=self.settings.log_level == "DEBUG",
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
        )

    def start(self) -> None:
        """Start the workflow monitor daemon."""
        logger.info("Starting workflow monitor daemon...")
        logger.info(f"Settings: {self.settings}")

        self.running = True
        try:
            while self.running:
                self._poll_and_execute()
                logger.info(f"Sleeping for {self.settings.daemon_poll_interval} seconds...")
                sleep(self.settings.daemon_poll_interval)
        except Exception as e:
            logger.error(f"Workflow monitor error: {e}")
            raise
        finally:
            logger.info("Workflow monitor stopped")

    def stop(self) -> None:
        """Stop the workflow monitor daemon."""
        logger.info("Stopping workflow monitor...")
        self.running = False

    def _poll_and_execute(self) -> None:
        """Poll for queued workflows and execute them."""
        with Session(bind=self.engine) as db:
            #######################
            # Find runs in RUNNING or INITIALIZING state
            logger.info("Checking for existing runs...")
            query = select(WorkflowRun).where(
                (WorkflowRun.state == WorkflowState.RUNNING) |
                (WorkflowRun.state == WorkflowState.INITIALIZING) |
                (WorkflowRun.state == '')
            )
            result = db.execute(query)
            existing_runs = result.scalars().all()
            logger.debug(f"Found {len(existing_runs)} existing runs to check")

            for run in existing_runs:
                self._check_run(db, run)

            #######################
            # Find QUEUED workflows
            logger.info("Checking for queued runs...")
            query = (
                select(WorkflowRun)
                .where(WorkflowRun.state == WorkflowState.QUEUED)
            )
            result = db.execute(query)
            queued_runs = result.scalars().all()
            logger.debug("Found %d queued runs", len(queued_runs))

            for run in queued_runs:
                # Start execution in background
                self._execute_run(db, run)

            #######################
            # Check for CANCELING workflows
            logger.info("Checking for canceling runs...")
            query = select(WorkflowRun).where(
                WorkflowRun.state == WorkflowState.CANCELING
            )
            result = db.execute(query)
            canceling_runs = result.scalars().all()
            logger.debug("Found %d canceling runs", len(canceling_runs))

            for run in canceling_runs:
                self._cancel_run(db, run)


    def _execute_run(self, db: Session, run: WorkflowRun) -> None:
        """
        Execute a workflow run.

        Args:
            run: WorkflowRun to execute
        """
        try:
            # Get run
            # Execute workflow
            logger.info(f"Executing run {run.id}")
            self.executor.execute(db, run)

        except Exception as e:
            logger.error(f"Error executing run {run.id}: {e}")
            # Create a new session for error handling to avoid transaction conflicts
            with Session(bind=self.engine) as error_db:
                result = error_db.execute(
                    select(WorkflowRun).where(WorkflowRun.id == run.id)
                )
                error_run = result.scalar_one_or_none()
                if error_run:
                    error_run.state = WorkflowState.SYSTEM_ERROR
                    error_run.end_time = datetime.now(timezone.utc)
                    error_run.system_logs.append(f"System error: {str(e)}")
                    error_db.commit()

    def _cancel_run(self, db: Session, run: WorkflowRun) -> None:
        """
        Cancel a workflow run.

        Args:
            db: Database session
            run: WorkflowRun to cancel
        """
        logger.info(f"Canceling run {run.id}")
        self.executor.cancel(db, run)

        # Update state to CANCELED
        run.state = WorkflowState.CANCELED
        run.end_time = datetime.now(timezone.utc)
        run.system_logs.append("Workflow canceled by user")

        db.commit()

    def _check_run(self, db: Session, run: WorkflowRun) -> None:
        """
        Check the status of a workflow run.

        Args:
            db: Database session
            run: WorkflowRun to check
        """
        logger.info(f"Checking run {run.id}")

        try:
            new_state = self.executor.get_run_state(db, run)
            if new_state != run.state:
                # Log status update
                log_msg = f"Run state update: {run.state} -> {new_state}"

                logger.info(f"Run {run.id}: {log_msg}")
                run.system_logs.append(log_msg)
                attributes.flag_modified(run, "system_logs")

                if new_state in [WorkflowState.COMPLETE, WorkflowState.EXECUTOR_ERROR,
                                 WorkflowState.CANCELED, WorkflowState.SYSTEM_ERROR]:
                    run.state = new_state
                    run.end_time = datetime.now(timezone.utc)

                db.commit()
        except Exception as e:
            logger.error(f"Error checking run {run.id}: {e}")

    def X_check_existing_runs(self, db: Session) -> None:
        """
        Check for existing runs in RUNNING or INITIALIZING state.

        This is used to monitor runs that were submitted before the daemon was started.

        Args:
            db: Database session
        """
        logger.info("Checking for existing runs in RUNNING or INITIALIZING state...")


        if existing_runs:

            for run in existing_runs:
                logger.info(f"Monitoring existing run {run.id} in state {run.state}")

                # TBD: Monitoring existing runs shoud be done in the executor, not here.
                # Check if the run has an Omics run ID
                omics_run_id = None
                if run.outputs and "omics_run_id" in run.outputs:
                    omics_run_id = run.outputs["omics_run_id"]
                    logger.info(f"Found Omics run ID {omics_run_id} for run {run.id}")

                if not omics_run_id:
                    # No Omics run ID found, mark as CANCELED
                    logger.warning((f"No Omics run ID found for run {run.id}, "
                                    f"marking as CANCELED"))
                    run.state = WorkflowState.CANCELED
                    run.end_time = datetime.now(timezone.utc)
                    run.system_logs.append("Run marked as CANCELED: No Omics run ID found")
                    db.commit()
        else:
            logger.info("No existing runs found to monitor")

    def X_monitor_existing_run(self, run_id: str, omics_run_id: str) -> None:
        """
        Monitor an existing run that was submitted before the daemon was started.

        Args:
            run_id: ID of the WorkflowRun to monitor
            omics_run_id: AWS Omics run ID
        """
        try:
            logger.info(f"Monitoring existing run {run_id} with Omics run ID {omics_run_id}")

            # Create a new database session for this task
            with Session(bind=self.engine) as db:
                # Get the run from the database
                result = db.execute(
                    select(WorkflowRun).where(WorkflowRun.id == run_id)
                )
                run = result.scalar_one_or_none()

                if not run:
                    logger.error(f"Run {run_id} not found")
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
                        run.end_time = datetime.now(timezone.utc)
                        run.system_logs.append((f"Run marked as CANCELED: Omics run {omics_run_id} "
                                                f"not found in AWS HealthOmics"))
                        run.exit_code = 1
                        db.commit()
                        return

                    # Monitor the run until completion
                    final_state = self.executor._monitor_omics_run(db, run, omics_run_id)

                    # Update run state based on Omics result
                    run.state = final_state
                    run.end_time = datetime.now(timezone.utc)

                    if final_state == WorkflowState.COMPLETE:
                        run.exit_code = 0
                        # Get outputs from Omics
                        try:
                            outputs = self.executor._get_run_outputs(omics_run_id)
                            run.outputs = outputs
                            db.commit()
                            logger.info(f"Committed outputs to database for run {run.id}")

                            # Update log URLs in the database
                            if 'logs' in outputs:
                                # Create a JSON structure with all log URLs
                                log_urls = {}

                                # Add run log URL
                                if 'run_log' in outputs['logs']:
                                    log_urls['run_log'] = outputs['logs']['run_log']

                                # Add manifest log URL
                                if 'manifest_log' in outputs['logs']:
                                    log_urls['manifest_log'] = outputs['logs']['manifest_log']

                                # Add task log URLs
                                if 'task_logs' in outputs['logs']:
                                    log_urls['task_logs'] = outputs['logs']['task_logs']

                                # Store all log URLs as JSON in stdout_url
                                run.stdout_url = json.dumps(log_urls)
                                db.commit()
                                logger.info(f"Run {run.id}: Set stdout_url to JSON structure "
                                            f"with all log URLs")
                                run.system_logs.append("Set stdout_url to JSON structure "
                                                       "with all log URLs")

                                # Still update individual task log entries
                                if 'task_logs' in outputs['logs']:
                                    self.executor._update_task_log_urls(
                                        db, run.id, outputs['logs']['task_logs']
                                    )

                                # Remove log URLs from outputs to avoid duplication
                                if 'logs' in run.outputs:
                                    del run.outputs['logs']
                                    from sqlalchemy.orm import attributes
                                    attributes.flag_modified(run, "outputs")
                                    db.commit()
                                    logger.info(f"Run {run.id}: Removed log URLs from outputs field")

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
                    db.commit()
                    logger.info(f"Committed state update for run {run.id} to database: {run.state}")
                else:
                    logger.warning((f"Executor is not OmicsExecutor, "
                                    f"cannot monitor existing run {run.id}"))

        except Exception as e:
            logger.error(f"Error monitoring existing run {run_id}: {e}")
            try:
                # Create a new session in case the previous one was closed or in an error state
                with Session(bind=self.engine) as error_db:
                    # Get the run again to update its state
                    result = error_db.execute(
                        select(WorkflowRun).where(WorkflowRun.id == run_id)
                    )
                    error_run = result.scalar_one_or_none()
                    if error_run:
                        error_run.state = WorkflowState.SYSTEM_ERROR
                        error_run.end_time = datetime.now(timezone.utc)
                        error_run.system_logs.append(
                            f"System error monitoring existing run: {str(e)}"
                        )
                        error_run.exit_code = 1
                        error_db.commit()
                        logger.info(f"Updated run {run_id} to SYSTEM_ERROR state due to exception")
            except Exception as inner_e:
                logger.error(f"Failed to update error state for run {run_id}: {inner_e}")


def main() -> None:
    """Main entry point for daemon."""
    monitor = WorkflowMonitor()
    try:
        monitor.start()
    except KeyboardInterrupt:
        monitor.stop()


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
        main()
    except KeyboardInterrupt:
        logger.info("Workflow monitor stopped by user")
    except Exception as e:
        logger.error(f"Unhandled exception in workflow monitor: {str(e)}", exc_info=True)
