from datetime import datetime, timedelta
from celery import shared_task
from app.services.aws_omics import HealthOmicsService
from app.models.workflow import WorkflowRun, TaskLog
from app.extensions import DB

@shared_task
def sync_and_cleanup_workflows():
    """Sync completed workflows from AWS HealthOmics to database and cleanup old runs"""
    omics_service = HealthOmicsService()
    
    # Get all runs from AWS HealthOmics that are in terminal states
    terminal_states = ['COMPLETED', 'FAILED', 'STOPPED']
    runs_to_delete = []
    
    try:
        response = omics_service.list_runs()
        for run in response.get('items', []):
            if run['status'] in terminal_states:
                # Check if run exists in database
                workflow_run = WorkflowRun.query.get(run['id'])
                if workflow_run and workflow_run.state not in ['COMPLETE', 'EXECUTOR_ERROR', 'CANCELED']:
                    # Get detailed run info before deletion
                    detailed_run = omics_service.get_run(run['id'])
                    
                    # Update run status
                    workflow_run.state = omics_service.map_run_state(run['status'])
                    workflow_run.end_time = run.get('stopTime')
                    workflow_run.output = detailed_run.get('output', {})
                    
                    # Store task information
                    for task in detailed_run.get('logStream', {}).get('tasks', []):
                        task_log = TaskLog(
                            id=task.get('taskId'),
                            run_id=run['id'],
                            name=task.get('name', 'unknown'),
                            cmd=task.get('command', []),
                            start_time=task.get('startTime'),
                            end_time=task.get('stopTime'),
                            stdout=f"s3://{detailed_run['outputUri']}/logs/{task['taskId']}/stdout.log",
                            stderr=f"s3://{detailed_run['outputUri']}/logs/{task['taskId']}/stderr.log",
                            exit_code=task.get('exitCode'),
                            system_logs=task.get('systemLogs', [])
                        )
                        DB.session.add(task_log)
                    
                    DB.session.commit()
                    
                    # Add to deletion list if run is older than 24 hours
                    if run.get('stopTime'):
                        stop_time = datetime.fromisoformat(run['stopTime'].replace('Z', '+00:00'))
                        if datetime.utcnow() - stop_time > timedelta(hours=24):
                            runs_to_delete.append(run['id'])
        
        # Delete runs from AWS HealthOmics
        for run_id in runs_to_delete:
            try:
                omics_service.delete_run(run_id)
                current_app.logger.info(f"Deleted run {run_id} from AWS HealthOmics")
            except Exception as e:
                current_app.logger.error(f"Failed to delete run {run_id}: {str(e)}")
                
    except Exception as e:
        current_app.logger.error(f"Error syncing workflows: {str(e)}")