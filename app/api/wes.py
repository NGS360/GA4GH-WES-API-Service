''' GA4GH WES API Implementation '''
#pylint: disable=missing-module-docstring, missing-class-docstring
from datetime import datetime
import os
from flask import current_app, request
from flask_restx import Namespace, Resource, fields
from app.models.workflow import WorkflowRun as WorkflowRunModel
from app.extensions import DB
from app.services.wes_factory import WesFactory

# Initialize WES service
wes_service = WesFactory.create_provider()

# Create namespace
api = Namespace('ga4gh/wes/v1', description='Workflow Execution Service API')

# Define API models
state_enum = ['UNKNOWN', 'QUEUED', 'INITIALIZING', 'RUNNING', 'PAUSED',
              'COMPLETE', 'EXECUTOR_ERROR', 'SYSTEM_ERROR', 'CANCELED', 'CANCELING']

run_request = api.model('RunRequest', {
    'workflow_params': fields.Raw(description='Workflow parameters'),
    'workflow_type': fields.String(required=True, description='Workflow type (CWL/WDL)'),
    'workflow_type_version': fields.String(required=True),
    'tags': fields.Raw(description='Optional key-value tags'),
    'workflow_engine_parameters': fields.Raw(),
    'workflow_engine': fields.String(),
    'workflow_engine_version': fields.String(),
    'workflow_url': fields.String(required=True)
})

run_log = api.model('RunLog', {
    'run_id': fields.String,
    'request': fields.Nested(run_request),
    'state': fields.String(enum=state_enum),
    'run_log': fields.Raw(),
    'task_logs': fields.List(fields.Raw()),
    'outputs': fields.Raw()
})

task_log = api.model('TaskLog', {
    'id': fields.String(required=True, description='Task ID'),
    'name': fields.String(required=True, description='Task name'),
    'cmd': fields.List(fields.String, description='Command executed'),
    'start_time': fields.String(description='Task start time'),
    'end_time': fields.String(description='Task end time'),
    'stdout': fields.String(description='URL to stdout logs'),
    'stderr': fields.String(description='URL to stderr logs'),
    'exit_code': fields.Integer(description='Exit code'),
    'system_logs': fields.List(fields.String, description='System logs')
})

task_list_response = api.model('TaskListResponse', {
    'task_logs': fields.List(fields.Nested(task_log)),
    'next_page_token': fields.String(description='Token for the next page')
})

@api.route('/service-info')
class ServiceInfo(Resource):
    def get(self):
        """Get service info"""
        return {
            'workflow_type_versions': {
                'CWL': {'workflow_type_version': ['1.0', '1.1']}
#                'WDL': {'workflow_type_version': ['1.0', '1.1']}
            },
            'supported_wes_versions': ['1.0.0'],
            'supported_filesystem_protocols': ['s3'],
            'workflow_engine_versions': {
                'aws-omics': '1.0'
            },
            'default_workflow_engine_parameters': [],
            'system_state_counts': {},
            'auth_instructions_url':
                'https://docs.aws.amazon.com/omics/latest/dev/what-is-service.html',
            'tags': {
                'workflow_engine': 'aws-omics'
            }
        }

@api.route('/runs')
class WorkflowRuns(Resource):
    @api.doc('list_runs')
    def get(self): # pylint: disable=inconsistent-return-statements
        """List workflow runs"""
        try:
            response = wes_service.list_runs()
            runs = []
            for run in response.get('items', []):
                runs.append({
                    'run_id': run['id'],
                    'state': wes_service.map_run_state(run['status'])
                })
            return {
                'runs': runs,
                'next_page_token': response.get('nextToken', '')
            }
        except Exception as e: # pylint: disable=broad-exception-caught
            current_app.logger.error(f"Failed to list runs: {str(e)}")
            api.abort(500, f"Failed to list runs: {str(e)}")

    @api.doc('run_workflow')
    @api.expect(run_request)
    def post(self): # pylint: disable=inconsistent-return-statements
        """Run a workflow"""
        try:
            workflow_params = api.payload.get('workflow_params', {})
            tags = api.payload.get('tags', {})

            # Start workflow run
            run_id = wes_service.start_run(
                workflow_id=api.payload['workflow_url'],
                parameters=workflow_params,
                output_uri=workflow_params.get('outputUri'),
                tags=tags
            )

            # Create local record
            new_run = WorkflowRunModel(
                run_id=run_id,
                state='QUEUED',
                workflow_type=api.payload['workflow_type'],
                workflow_type_version=api.payload['workflow_type_version'],
                workflow_url=api.payload['workflow_url'],
                workflow_params=workflow_params,
                workflow_engine='aws-omics',
                tags=tags,
                start_time=datetime.utcnow()
            )
            DB.session.add(new_run)
            DB.session.commit()

            return {'run_id': run_id}
        except Exception as e: # pylint: disable=broad-exception-caught
            current_app.logger.error(f"Failed to start run: {str(e)}")
            api.abort(500, f"Failed to start run: {str(e)}")

@api.route('/runs/<string:run_id>')
class WorkflowRun(Resource):
    def get(self, run_id): # pylint: disable=inconsistent-return-statements
        """Get detailed run log"""
        try:
            run = wes_service.get_run(run_id)

            state = wes_service.map_run_state(run['status'])
            start_time = run.get('startTime')
            end_time = run.get('stopTime')

            return {
                'run_id': run_id,
                'state': state,
                'run_log': {
                    'name': run.get('name', 'workflow'),
                    'start_time': start_time.isoformat() if start_time else None,
                    'end_time': end_time.isoformat() if end_time else None,
                    'stdout': run.get('outputUri'),
                    'stderr': run.get('logStream')
                },
                'task_logs': [],  # AWS HealthOmics doesn't provide detailed task logs
                'outputs': run.get('output', {})
            }
        except Exception as e: # pylint: disable=broad-exception-caught
            current_app.logger.error(f"Failed to get run {run_id}: {str(e)}")
            api.abort(500, f"Failed to get run {run_id}: {str(e)}")

@api.route('/runs/<string:run_id>/status')
class WorkflowRunStatus(Resource):
    def get(self, run_id): # pylint: disable=inconsistent-return-statements
        """Get run status"""
        try:
            run = wes_service.get_run(run_id)
            return {
                'run_id': run_id,
                'state': wes_service.map_run_state(run['status'])
            }
        except Exception as e: # pylint: disable=broad-exception-caught
            current_app.logger.error(f"Failed to get run status {run_id}: {str(e)}")
            api.abort(500, f"Failed to get run status {run_id}: {str(e)}")

@api.route('/runs/<string:run_id>/cancel')
class WorkflowRunCancel(Resource):
    def post(self, run_id): # pylint: disable=inconsistent-return-statements
        """Cancel a run"""
        try:
            wes_service.cancel_run(run_id)
            return {'run_id': run_id}
        except Exception as e: # pylint: disable=broad-exception-caught
            current_app.logger.error(f"Failed to cancel run {run_id}: {str(e)}")
            api.abort(500, f"Failed to cancel run {run_id}: {str(e)}")

@api.route('/runs/<string:run_id>/tasks')
class WorkflowTasks(Resource):
    @api.doc('list_tasks')
    @api.marshal_with(task_list_response)
    def get(self, run_id): # pylint: disable=inconsistent-return-statements
        """List tasks for a workflow run"""
        try:
            # Get AWS HealthOmics run details
            run = wes_service.get_run(run_id)

            # Get pagination parameters
            page_size = request.args.get('page_size', 100, type=int)
            page_token = request.args.get('page_token', None)

            # Extract task information from the run
            tasks = []

            # AWS HealthOmics provides task information in the run logs
            for task in run.get('logStream', {}).get('tasks', []):
                task_log_instance = {
                    'id': task.get('taskId'),
                    'name': task.get('name', 'unknown'),
                    'cmd': task.get('command', []),
                    'start_time': task.get('startTime'),
                    'end_time': task.get('stopTime'),
                    'stdout': f"s3://{run['outputUri']}/logs/{task['taskId']}/stdout.log",
                    'stderr': f"s3://{run['outputUri']}/logs/{task['taskId']}/stderr.log",
                    'exit_code': task.get('exitCode'),
                    'system_logs': task.get('systemLogs', [])
                }
                tasks.append(task_log_instance)

            # Implement basic pagination
            start_idx = 0
            if page_token:
                start_idx = int(page_token)

            end_idx = start_idx + page_size
            current_tasks = tasks[start_idx:end_idx]

            # Generate next page token
            next_token = ''
            if end_idx < len(tasks):
                next_token = str(end_idx)

            return {
                'task_logs': current_tasks,
                'next_page_token': next_token
            }

        except Exception as e: # pylint: disable=broad-exception-caught
            current_app.logger.error(f"Failed to list tasks for run {run_id}: {str(e)}")
            api.abort(500, f"Failed to list tasks: {str(e)}")

@api.route('/runs/<string:run_id>/tasks/<string:task_id>')
class WorkflowTask(Resource):
    @api.doc('get_task')
    @api.marshal_with(task_log)
    def get(self, run_id, task_id): # pylint: disable=inconsistent-return-statements
        """Get task details"""
        try:
            # Get run details
            run = wes_service.get_run(run_id)

            # Find the specific task
            task = None
            for t in run.get('logStream', {}).get('tasks', []):
                if t.get('taskId') == task_id:
                    task = t
                    break

            if not task:
                api.abort(404, f"Task {task_id} not found in run {run_id}")

            # Format task information
            return {
                'id': task.get('taskId'),
                'name': task.get('name', 'unknown'),
                'cmd': task.get('command', []),
                'start_time': task.get('startTime'),
                'end_time': task.get('stopTime'),
                'stdout': f"s3://{run['outputUri']}/logs/{task_id}/stdout.log",
                'stderr': f"s3://{run['outputUri']}/logs/{task_id}/stderr.log",
                'exit_code': task.get('exitCode'),
                'system_logs': task.get('systemLogs', [])
            }

        except Exception as e: # pylint: disable=broad-exception-caught
            current_app.logger.error(f"Failed to get task {task_id} for run {run_id}: {str(e)}")
            api.abort(500, f"Failed to get task: {str(e)}")
