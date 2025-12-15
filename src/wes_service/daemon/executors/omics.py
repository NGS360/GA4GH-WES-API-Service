"""AWS Omics workflow executor implementation."""

import boto3
from datetime import datetime
import asyncio
import json
import logging
from typing import Dict, Any, Union, List

from sqlalchemy.ext.asyncio import AsyncSession

from src.wes_service.daemon.executors.base import WorkflowExecutor
from src.wes_service.db.models import TaskLog, WorkflowRun, WorkflowState
from src.wes_service.config import get_settings

from sqlalchemy.orm import attributes

logger = logging.getLogger(__name__)


class OmicsExecutor(WorkflowExecutor):
    """Executor for AWS Omics workflows."""
    def __init__(self, region_name=None):
        """
        Initialize with AWS region.

        Args:
            region_name: AWS region name (defaults to config setting)
        """
        settings = get_settings()
        self.region = region_name or settings.omics_region
        self.role_arn = settings.omics_role_arn
        self.output_bucket = settings.omics_output_bucket

        self.omics_client = boto3.client('omics', region_name=self.region)
        self.s3_client = boto3.client('s3', region_name=self.region)

    async def execute(self, db: AsyncSession, run: WorkflowRun) -> None:
        """
        Execute a workflow run on AWS Omics.

        Args:
            db: Database session
            run: WorkflowRun to execute
        """
        omics_run_id = None
        try:
            # Update state to INITIALIZING
            run.state = WorkflowState.INITIALIZING
            timestamp = datetime.utcnow().isoformat()
            run.system_logs.append(f"Initializing AWS Omics workflow at {timestamp}")
            await db.commit()
            logger.info(f"Run {run.id}: Initializing AWS Omics workflow")

            # Extract workflow ID from workflow_url or params
            try:
                workflow_id = self._extract_workflow_id(run)
                run.system_logs.append(f"Using Omics workflow ID: {workflow_id}")
            except Exception as e:
                error_msg = f"Failed to extract workflow ID: {str(e)}"
                logger.error(f"Run {run.id}: {error_msg}")
                run.system_logs.append(error_msg)
                run.state = WorkflowState.SYSTEM_ERROR
                run.end_time = datetime.utcnow()
                run.exit_code = 1
                await db.commit()
                return

            # Extract and convert input parameters
            input_params = run.workflow_params or {}
            run.system_logs.append(f"Input parameters: {input_params}")

            # Convert WES parameters to Omics format
            omics_params = self._convert_params_to_omics(input_params, run.workflow_type)
            run.system_logs.append(f"Omics parameters: {omics_params}")
            await db.commit()

            # Update state to RUNNING
            run.state = WorkflowState.RUNNING
            run.start_time = datetime.utcnow()
            run.system_logs.append(f"Started execution at {run.start_time.isoformat()}")
            await db.commit()
            logger.info(f"Run {run.id}: Starting workflow execution")

            # Start the Omics workflow run
            try:
                # Set default output URI if not provided in workflow_engine_parameters
                output_uri = None
                if run.workflow_engine_parameters and 'outputUri' in run.workflow_engine_parameters:
                    output_uri = run.workflow_engine_parameters['outputUri']
                    logger.info(f"Using output URI from workflow_engine_parameters: {output_uri}")
                else:
                    output_uri = f"{self.output_bucket}/runs/{run.id}/output/"
                    logger.info(f"Using default output URI: {output_uri}")

                # Set default parameters for the API call
                kwargs = {
                    'workflowId': workflow_id,
                    'roleArn': self.role_arn,
                    'parameters': omics_params,
                    'outputUri': output_uri,
                    'name': f"wes-run-{run.id}",
                    'retentionMode': 'REMOVE',
                    'storageType': 'DYNAMIC'
                }

                # Add tags from the run object
                if run.tags and len(run.tags) > 0:
                    kwargs['tags'] = run.tags
                    logger.info(f"Adding tags to Omics run: {run.tags}")
                    if "Name" in run.tags:
                        kwargs['name'] = run.tags.get("Name")

                # Extract and add Omics-specific parameters from workflow_engine_parameters
                if run.workflow_engine_parameters:
                    engine_params = run.workflow_engine_parameters
                    # Override name if provided
                    if 'name' in engine_params:
                        kwargs['name'] = engine_params['name']

                    # Add run group ID if specified
                    if 'runGroupId' in engine_params:
                        kwargs['runGroupId'] = engine_params['runGroupId']
                        logger.info(f"Using run group ID: {engine_params['runGroupId']}")

                    # Add cache ID for reusing previous runs
                    if 'cacheId' in engine_params:
                        kwargs['cacheId'] = engine_params['cacheId']
                        logger.info(f"Using cached run ID: {engine_params['cacheId']}")

                    # Add tags if provided
                    if 'tags' in engine_params:
                        kwargs['tags'] = engine_params['tags']

                    # Add other supported parameters
                    omics_params = [
                        'priority', 'storageCapacity', 'accelerators', 'logLevel', 'storageType'
                    ]
                    for param in omics_params:
                        if param in engine_params:
                            kwargs[param] = engine_params[param]

                # Log the API call parameters
                logger.info(f"Starting Omics run with parameters: {kwargs}")

                # Make the API call to start the run
                response = self.omics_client.start_run(**kwargs)

                # Store the Omics run ID
                omics_run_id = response['id']
                log_msg = f"Started AWS Omics run: {omics_run_id}, output will be in: {output_uri}"
                run.system_logs.append(log_msg)
                logger.info(f"Run {run.id}: {log_msg}")

                # Store the Omics run ID in the outputs field for reference
                if not run.outputs:
                    run.outputs = {}
                run.outputs['omics_run_id'] = omics_run_id

                # Store the output location with the run ID appended
                # If the URI doesn't end with a slash, add one
                if not output_uri.endswith('/'):
                    output_uri += '/'
                # Append the run ID to create the complete output path
                complete_output_uri = f"{output_uri}{omics_run_id}"
                run.outputs['output_location'] = complete_output_uri
                logger.info(f"Set output_location to {complete_output_uri} for run {run.id}")

                await db.commit()
            except Exception as e:
                error_msg = f"Failed to start Omics workflow: {str(e)}"
                logger.error(f"Run {run.id}: {error_msg}")
                run.system_logs.append(error_msg)
                run.state = WorkflowState.SYSTEM_ERROR
                run.end_time = datetime.utcnow()
                run.exit_code = 1
                await db.commit()
                return

            # Monitor the run until completion
            try:
                final_state = await self._monitor_omics_run(db, run, omics_run_id)

                # Update run state based on Omics result
                run.state = final_state
                run.end_time = datetime.utcnow()

                if final_state == WorkflowState.COMPLETE:
                    run.exit_code = 0
                    # Get outputs from Omics
                    try:
                        outputs = await self._get_run_outputs(omics_run_id)
                        run.outputs = outputs
                        attributes.flag_modified(run, "outputs")
                        await db.commit()
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
                            logger.info(f"Run {run.id}: Set stdout_url to "
                                        f"JSON structure with all log URLs")
                            run.system_logs.append(f"Set stdout_url to "
                                                   f"JSON structure with all log URLs")

                            # Remove log URLs from outputs to avoid duplication
                            if 'logs' in run.outputs:
                                del run.outputs['logs']
                                attributes.flag_modified(run, "outputs")
                                logger.info(f"Run {run.id}: Removed log URLs from outputs field")

                            # Explicitly commit the change to ensure it's saved
                            await db.commit()
                            logger.info(f"Run {run.id}: Committed log URLs to database")

                            # Update task log URLs
                            if 'task_logs' in outputs['logs']:
                                task_logs = outputs['logs']['task_logs']
                                await self._update_task_log_urls(db, run.id, task_logs)

                        log_msg = f"Workflow completed successfully at {run.end_time.isoformat()}"
                        run.system_logs.append(log_msg)
                        logger.info(f"Run {run.id}: {log_msg}")
                    except Exception as e:
                        error_msg = f"Workflow completed but failed to retrieve outputs: {str(e)}"
                        logger.warning(f"Run {run.id}: {error_msg}")
                        run.system_logs.append(error_msg)
                        # Still mark as complete even if we couldn't get outputs
                else:
                    run.exit_code = 1
                    end_time = run.end_time.isoformat()
                    log_msg = f"Workflow failed with state {final_state} at {end_time}"
                    run.system_logs.append(log_msg)
                    logger.error(f"Run {run.id}: {log_msg}")

                await db.commit()
            except Exception as e:
                error_msg = f"Error monitoring workflow: {str(e)}"
                logger.error(f"Run {run.id}: {error_msg}")
                run.system_logs.append(error_msg)
                run.state = WorkflowState.SYSTEM_ERROR
                run.end_time = datetime.utcnow()
                run.exit_code = 1
                await db.commit()
                return

            # Double check the AWS status if we marked as error
            error_states = [WorkflowState.EXECUTOR_ERROR, WorkflowState.SYSTEM_ERROR]
            if run.state in error_states and omics_run_id:
                try:
                    aws_status = self.omics_client.get_run(id=omics_run_id).get('status')
                    if aws_status == 'COMPLETED':
                        # AWS shows completed but we marked as error - override to completed
                        log_msg = (
                            f"AWS reports workflow as COMPLETED but WES had error state "
                            f"{run.state}. Setting to COMPLETE.")
                        logger.warning(f"Run {run.id}: {log_msg}")
                        run.system_logs.append(log_msg)
                        run.state = WorkflowState.COMPLETE
                        run.exit_code = 0
                        await db.commit()
                except Exception as aws_check_error:
                    log_msg = f"Failed to double-check AWS run status: {str(aws_check_error)}"
                    run.system_logs.append(log_msg)
                    logger.error(f"Run {run.id}: {log_msg}")

        except Exception as e:
            error_msg = f"Unhandled error executing Omics run: {str(e)}"
            logger.error(f"Run {run.id}: {error_msg}")

            # Handle errors
            run.state = WorkflowState.SYSTEM_ERROR
            run.end_time = datetime.utcnow()
            run.system_logs.append(error_msg)
            run.exit_code = 1

            # Double check AWS status if possible
            if omics_run_id:
                try:
                    aws_status = self.omics_client.get_run(id=omics_run_id).get('status')
                    status_msg = f"Current AWS Omics status is: {aws_status}"
                    logger.info(f"Run {run.id}: {status_msg}")
                    run.system_logs.append(status_msg)

                    if aws_status == 'COMPLETED':
                        # If AWS shows completed but we got an error, override to completed
                        override_msg = ("AWS reports workflow as COMPLETED despite error. "
                                        "Setting state to COMPLETE.")
                        logger.warning(f"Run {run.id}: {override_msg}")
                        run.system_logs.append(override_msg)
                        run.state = WorkflowState.COMPLETE
                        run.exit_code = 0
                except Exception as aws_check_error:
                    run.system_logs.append(f"Failed to check AWS status: {str(aws_check_error)}")

            await db.commit()

    def _extract_workflow_id(self, run: WorkflowRun) -> str:
        """
        Extract Omics workflow ID from run parameters.
        Args:
            run: The workflow run
        Returns:
            Omics workflow ID
        """
        # Option 1: Extract from workflow_url if it contains the ID
        if run.workflow_url and run.workflow_url.startswith("omics:"):
            return run.workflow_url.split(":")[-1]

        # Option 2: Look for workflow_id in parameters
        if run.workflow_params and "workflow_id" in run.workflow_params:
            return run.workflow_params["workflow_id"]

        # Option 3: Use the workflow_url directly if it looks like an ID
        return run.workflow_url

    def _convert_params_to_omics(
        self, wes_params: Dict[str, Any], workflow_type: str
    ) -> Dict[str, Any]:
        """
        Convert WES parameters to Omics format.

        Args:
            wes_params: WES API parameters
            workflow_type: Type of workflow (CWL, WDL, etc.)

        Returns:
            Parameters in Omics format
        """
        omics_params = {}

        # Log the incoming parameters for debugging
        logger.info(
            f"Converting WES parameters to Omics format for {workflow_type} workflow: {wes_params}"
        )

        try:
            # Map input file paths to Omics parameter format
            for key, value in wes_params.items():
                if key == "workflow_id":
                    # Skip the workflow_id if present
                    continue

                elif isinstance(value, list):
                    # Handle list of files or other objects
                    processed_list = []
                    for item in value:
                        if isinstance(item, dict) and item.get("class") == "File" and "path" in item:
                            # For CWL workflows, preserve the File object structure
                            if workflow_type == "CWL":
                                processed_list.append(item)
                            else:
                                # For other workflow types, extract just the path
                                processed_list.append(item["path"])
                        else:
                            # Keep as is
                            processed_list.append(item)
                    omics_params[key] = processed_list

                elif isinstance(value, dict) and value.get("class") == "File" and "path" in value:
                    # For CWL workflows, preserve the File object structure
                    if workflow_type == "CWL":
                        omics_params[key] = value
                    else:
                        # For other workflow types, extract just the path
                        omics_params[key] = value["path"]

                elif isinstance(value, str) and (value.startswith("s3://") or value.startswith("/")):
                    # This is likely a file path
                    omics_params[key] = value

                else:
                    # Other parameters
                    omics_params[key] = value

            logger.info(f"Converted parameters for Omics: {omics_params}")
            return omics_params

        except Exception as e:
            logger.error(f"Error converting parameters to Omics format: {str(e)}")
            # Return original params to avoid breaking the workflow
            return wes_params

    async def _monitor_omics_run(
        self, db: AsyncSession, run: WorkflowRun, omics_run_id: str
    ) -> WorkflowState:
        """
        Monitor Omics run until completion.

        Args:
            db: Database session
            run: The workflow run
            omics_run_id: Omics run ID

        Returns:
            Final workflow state
        """
        poll_interval = get_settings().daemon_poll_interval

        try:
            while True:
                # Get run status from Omics
                try:
                    response = self.omics_client.get_run(id=omics_run_id)
                    status = response.get('status', 'UNKNOWN')

                    # Log status update
                    log_msg = f"Omics status update: {status}"
                    logger.info(f"Run {run.id}: {log_msg}")
                    run.system_logs.append(log_msg)
                    await db.commit()

                    # Update task logs if available
                    if 'tasks' in response:
                        await self._update_task_logs(db, run, response['tasks'])

                    # Map Omics status to WES status
                    if status == 'COMPLETED':
                        # Get outputs including output mapping
                        outputs = await self._get_run_outputs(omics_run_id)
                        logger.info("checkpoint1:"+str(outputs))
                        if outputs:
                            run.outputs.update(outputs)
                            await db.commit()
                            logger.info(f"Updated run outputs with output mapping for run {run.id}")
                        return WorkflowState.COMPLETE
                    elif status == 'FAILED':
                        error_message = response.get('message', 'No error message')
                        log_msg = f"Omics workflow failed: {error_message}"
                        run.system_logs.append(log_msg)
                        await db.commit()
                        return WorkflowState.EXECUTOR_ERROR
                    elif status in ['CANCELLED', 'CANCELLED_RUNNING', 'CANCELLED_STARTING']:
                        return WorkflowState.CANCELED
                    elif status in ['STARTING', 'RUNNING', 'PENDING', 'QUEUED']:
                        # Still running, wait and check again
                        await asyncio.sleep(poll_interval)
                    elif status in ['STOPPING', 'TERMINATING']:
                        # Workflow is in transition state, continue monitoring
                        log_msg = f"Omics workflow in transition state: {status}"
                        run.system_logs.append(log_msg)
                        await db.commit()
                        await asyncio.sleep(poll_interval)
                    else:
                        # Unknown status
                        log_msg = f"Unknown Omics status: {status}"
                        run.system_logs.append(log_msg)
                        await db.commit()
                        return WorkflowState.SYSTEM_ERROR

                except Exception as e:
                    error_msg = f"Error monitoring Omics run: {str(e)}"
                    logger.error(f"Run {run.id}: {error_msg}")
                    run.system_logs.append(error_msg)
                    await db.commit()
                    return WorkflowState.SYSTEM_ERROR

        except Exception as e:
            error_msg = f"Unexpected error in monitor_omics_run: {str(e)}"
            logger.error(f"Run {run.id}: {error_msg}")
            run.system_logs.append(error_msg)
            await db.commit()
            return WorkflowState.SYSTEM_ERROR

    async def _update_task_logs(self, db: AsyncSession, run: WorkflowRun, tasks: list) -> None:
        """
        Update task logs from Omics tasks.

        Args:
            db: Database session
            run: The workflow run
            tasks: Omics task data
        """
        for task_data in tasks:
            # Create task ID
            task_id = f"omics-{task_data['id']}"

            # Parse dates if available
            start_time = None
            if 'startTime' in task_data:
                try:
                    start_time = datetime.fromisoformat(
                        task_data['startTime'].replace('Z', '+00:00')
                    )
                except (ValueError, TypeError):
                    pass

            end_time = None
            if 'stopTime' in task_data:
                try:
                    end_time = datetime.fromisoformat(task_data['stopTime'].replace('Z', '+00:00'))
                except (ValueError, TypeError):
                    pass

            # Create or update task log
            task = TaskLog(
                id=task_id,
                run_id=run.id,
                name=task_data.get('name', 'Unknown task'),
                cmd=[],  # Omics doesn't expose the command
                start_time=start_time,
                end_time=end_time,
                exit_code=0 if task_data.get('status') == 'COMPLETED' else 1,
                system_logs=[f"Omics task status: {task_data.get('status')}"]
            )

            db.add(task)

        await db.commit()

    async def _update_task_log_urls(
        self, db: AsyncSession, run_id: str, task_logs: Dict[str, str]
    ) -> None:
        """
        Update task log URLs in the database.

        Args:
            db: Database session
            run_id: Run ID
            task_logs: Dictionary mapping task names to log URLs
        """
        # Import needed here to avoid circular imports
        from sqlalchemy import select

        for task_name, log_url in task_logs.items():
            # Find task by name
            query = select(TaskLog).where(
                TaskLog.run_id == run_id,
                TaskLog.name == task_name
            )
            result = await db.execute(query)
            task = result.scalar_one_or_none()

            if task:
                # Update task log URL
                task.stdout_url = log_url
                logger.info(f"Task {task.id}: Set stdout_url to {log_url}")
                # Add debug log to verify task stdout_url is being set
                task.system_logs.append(f"Set stdout_url to {log_url}")
            else:
                logger.warning(f"Task with name '{task_name}' not found for run {run_id}")

        # Explicitly commit changes
        await db.commit()
        logger.info(f"Committed task log URLs to database for run {run_id}")

    def _ensure_json_serializable(self, obj: Any) -> Union[Dict, List, str, int, float, bool, None]:
        """
        Ensure an object is JSON serializable by converting non-serializable types.

        Args:
            obj: Any Python object

        Returns:
            JSON serializable version of the object
        """
        if isinstance(obj, dict):
            return {k: self._ensure_json_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._ensure_json_serializable(item) for item in obj]
        elif isinstance(obj, (datetime, )):
            return obj.isoformat() if hasattr(obj, 'isoformat') else str(obj)
        elif isinstance(obj, (int, float, str, bool, type(None))):
            return obj
        else:
            return str(obj)

    async def _get_run_outputs(self, omics_run_id: str) -> Dict[str, Any]:
        """
        Get outputs from completed Omics run.

        Args:
            omics_run_id: Omics run ID

        Returns:
            Dictionary of outputs
        """
        try:
            logger.info(f"Fetching outputs for Omics run {omics_run_id}")
            response = self.omics_client.get_run(id=omics_run_id)

            # Extract only the most relevant output information
            outputs = {}

            # Store the Omics run ID in the outputs
            outputs['omics_run_id'] = omics_run_id

            # Primary output: the output location
            if 'outputUri' in response:
                output_uri = response['outputUri']
                outputs['output_location'] = output_uri
                logger.info(f"Set output_location to {output_uri} for run {omics_run_id}")

            # Log the full response for debugging
            logger.debug(f"Full AWS Omics response for run {omics_run_id}: {response}")

            # Handle CloudWatch Logs format in logLocation
            if 'logLocation' in response:
                logger.info(f"Found logLocation in response: {response['logLocation']}")

                # Extract CloudWatch log information
                if 'runLogStream' in response['logLocation']:
                    run_log_stream = response['logLocation']['runLogStream']
                    logger.info(f"Found runLogStream: {run_log_stream}")

                    # CloudWatch logs format:
                    # arn:aws:logs:region:account:log-group:name:log-stream:name
                    if run_log_stream.startswith('arn:aws:logs:'):
                        # Extract the log group and log stream
                        parts = run_log_stream.split(':')
                        if len(parts) >= 8:
                            region = parts[3]
                            log_group = parts[6]

                            # Extract the actual run ID from the ARN
                            arn_parts = run_log_stream.split(':log-stream:')
                            if len(arn_parts) == 2:
                                log_stream = arn_parts[1]  # This should be "run/5721106"
                                logger.info(f"Extracted log stream from ARN: {log_stream}")
                            else:
                                # Fallback to the old method if the format is different
                                log_stream_parts = parts[7:]
                                log_stream = ':'.join(log_stream_parts)
                                logger.info(f"Fallback log stream extraction: {log_stream}")

                            # Log the extracted values for debugging
                            logger.info(
                                (f"Extracted region: {region}, log_group: {log_group}, "
                                 f"log_stream: {log_stream}")
                            )

                            # Construct CloudWatch log URL with proper URL encoding
                            cloudwatch_url = (
                                f"https://{region}.console.aws.amazon.com/cloudwatch/home"
                                f"?region={region}#logsV2:log-groups/log-group/"
                                f"{log_group.replace('/', '%2F')}"
                                f"/log-events/{log_stream.replace('/', '%2F')}"
                            )

                            # Add to outputs
                            outputs['logs'] = {
                                'run_log': cloudwatch_url,
                                'log_group': log_group,
                                'log_stream': log_stream
                            }

                            logger.info(f"Created CloudWatch log URL: {cloudwatch_url}")

                            # Try to construct task-specific log URLs if possible
                            # Format is typically: task/{runId}/{taskId}
                            run_id_match = log_stream.split('/')
                            if len(run_id_match) >= 2 and run_id_match[0] == 'run':
                                run_id = run_id_match[1]

                                # Get the actual run ID from the log stream (format: run/XXXXXXX)
                                run_id_parts = log_stream.split('/')
                                if len(run_id_parts) >= 2 and run_id_parts[0] == 'run':
                                    run_id = run_id_parts[1]
                                    logger.info(f"Extracted run ID: {run_id}")

                                    # Create task log URL - use the actual run ID
                                    task_log_stream = f"task/{run_id}/main"
                                    task_log_url = (
                                        f"https://{region}.console.aws.amazon.com/cloudwatch/home"
                                        f"?region={region}#logsV2:log-groups/log-group/"
                                        f"{log_group.replace('/', '%2F')}"
                                        f"/log-events/{task_log_stream.replace('/', '%2F')}"
                                    )

                                    # Create manifest log URL - use the actual run ID
                                    manifest_log_stream = f"manifest/run/{run_id}"
                                    manifest_log_url = (
                                        f"https://{region}.console.aws.amazon.com/cloudwatch/home"
                                        f"?region={region}#logsV2:log-groups/log-group/"
                                        f"{log_group.replace('/', '%2F')}"
                                        f"/log-events/{manifest_log_stream.replace('/', '%2F')}"
                                    )

                                # Add task logs
                                outputs['logs']['task_logs'] = {
                                    'main': task_log_url
                                }

                                # Add manifest log
                                outputs['logs']['manifest_log'] = manifest_log_url

                                logger.info(f"Created task log URL: {task_log_url}")
                                logger.info(f"Created manifest log URL: {manifest_log_url}")
                            else:
                                # Fallback to using the same URL for task logs
                                outputs['logs']['task_logs'] = {
                                    'main': cloudwatch_url
                                }
                    else:
                        logger.warning(
                            (f"runLogStream doesn't match expected CloudWatch ARN format: "
                             f"{run_log_stream}")
                        )
                else:
                    logger.warning(
                        f"No runLogStream found in logLocation: {response['logLocation']}"
                    )
            else:
                logger.warning(f"No logLocation found in response for run {omics_run_id}")

            # Include actual workflow outputs if available
            if 'outputs' in response:
                outputs['workflow_outputs'] = response['outputs']

            # Add error message if there was an error
            if 'message' in response and response['status'] != 'COMPLETED':
                outputs['error_message'] = response['message']

            logger.info(f"Successfully retrieved outputs for Omics run {omics_run_id}")
            # Log the outputs for debugging
            logger.debug(f"Outputs for run {omics_run_id}: {outputs}")
            # Try to fetch output mapping from S3 if output_location is available
            if 'output_location' in outputs:
                try:
                    output_mapping = await self._fetch_output_mapping(
                                            outputs['output_location'], omics_run_id
                    )
                    if output_mapping:
                        outputs['output_mapping'] = output_mapping
                        logger.info(f"Added output mapping to outputs for run {omics_run_id}")
                        logger.info(f"{outputs['output_mapping']}")
                except Exception as e:
                    logger.warning(f"Failed to fetch output mapping for run "
                                   f"{omics_run_id}: {str(e)}")

            # Ensure all values are JSON serializable
            return self._ensure_json_serializable(outputs)

        except Exception as e:
            error_msg = f"Error getting outputs for Omics run {omics_run_id}: {str(e)}"
            logger.error(error_msg)
            return {"error": error_msg}

    async def _fetch_output_mapping(self, output_uri: str, omics_run_id: str) -> Dict[str, str]:
        """
        Fetch output mapping from S3.

        Args:
            output_uri: S3 URI of the output directory
            omics_run_id: Omics run ID

        Returns:
            Dictionary mapping output names to S3 URIs
        """
        try:
            # Parse S3 URI
            if not output_uri.startswith('s3://'):
                logger.warning(f"Output URI {output_uri} is not an S3 URI")
                return {}

            # Remove s3:// prefix and split into bucket and key
            path = output_uri[5:]
            parts = path.split('/', 1)
            if len(parts) < 2:
                logger.warning(f"Invalid S3 URI format: {output_uri}")
                return {}

            bucket = parts[0]
            key_prefix = parts[1]

            # Ensure key prefix ends with a slash
            if not key_prefix.endswith('/'):
                key_prefix += '/'

            # The specific path to the outputs.json file based on the example
            # s3://bucket/path/to/output/run_id/logs/outputs.json
            output_json_key = f"{key_prefix}{omics_run_id}/logs/outputs.json"

            # Try to fetch the output mapping file
            try:
                logger.info(f"Attempting to fetch output mapping from "
                            f"s3://{bucket}/{output_json_key}")
                response = self.s3_client.get_object(Bucket=bucket, Key=output_json_key)
                content = response['Body'].read().decode('utf-8')
                mapping = json.loads(content)

                # Validate mapping format
                if isinstance(mapping, dict):
                    # Convert CWL-style output format to a simpler key-value mapping
                    result = {}
                    for key, value in mapping.items():
                        if isinstance(value, dict) and 'location' in value:
                            # Extract the S3 URI from the location field
                            result[key] = value['location']
                        elif (isinstance(value, list) and
                            all(isinstance(item, dict) and 'location' in item for item in value)):
                            # For array outputs, extract all locations
                            result[key] = [item['location'] for item in value]
                        else:
                            # For other types, just convert to string
                            result[key] = str(value)

                    logger.info(f"Successfully loaded output mapping with {len(result)} entries")
                    return result
                else:
                    logger.warning(f"Output mapping file s3://{bucket}/{output_json_key} "
                                   f"is not a dictionary")
            except self.s3_client.exceptions.NoSuchKey:
                logger.info(f"Output mapping file s3://{bucket}/{output_json_key} not found")
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse output mapping file "
                               f"s3://{bucket}/{output_json_key} as JSON")
            except Exception as e:
                logger.warning(f"Error accessing s3://{bucket}/{output_json_key}: {str(e)}")

            # If we get here, we couldn't find a valid output mapping file
            logger.warning(f"No valid output mapping file found for run {omics_run_id}")
            return {}

        except Exception as e:
            logger.error(f"Error fetching output mapping for run {omics_run_id}: {str(e)}")
            return {}
