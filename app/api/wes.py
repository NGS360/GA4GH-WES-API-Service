''' GA4GH WES API Implementation '''
#pylint: disable=missing-module-docstring, missing-class-docstring
from datetime import datetime
import uuid
import os
from flask import current_app
from flask_restx import Namespace, Resource, fields
from app.models.workflow import WorkflowRunModel, TaskLog
from app.extensions import DB
from app.services.aws_omics import HealthOmicsService

# Initialize AWS HealthOmics service
omics_service = HealthOmicsService()

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
            'auth_instructions_url': 'https://docs.aws.amazon.com/omics/latest/dev/what-is-service.html',
            'tags': {
                'workflow_engine': 'aws-omics'
            }
        }

@api.route('/runs')
class WorkflowRuns(Resource):
    @api.doc('list_runs')
    def get(self):
        """List workflow runs"""
        try:
            response = omics_service.list_runs()
            runs = []
            for run in response.get('items', []):
                runs.append({
                    'run_id': run['id'],
                    'state': omics_service.map_run_state(run['status'])
                })
            return {
                'runs': runs,
                'next_page_token': response.get('nextToken', '')
            }
        except Exception as e:
            current_app.logger.error(f"Failed to list runs: {str(e)}")
            api.abort(500, f"Failed to list runs: {str(e)}")

    @api.doc('run_workflow')
    @api.expect(run_request)
    def post(self):
        """Run a workflow"""
        try:
            workflow_params = api.payload.get('workflow_params', {})
            tags = api.payload.get('tags', {})
            
            # Start AWS HealthOmics workflow run
            run_id = omics_service.start_run(
                workflow_id=api.payload['workflow_url'],
                role_arn=os.environ['AWS_OMICS_ROLE_ARN'],
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
        except Exception as e:
            current_app.logger.error(f"Failed to start run: {str(e)}")
            api.abort(500, f"Failed to start run: {str(e)}")

@api.route('/runs/<string:run_id>')
class WorkflowRun(Resource):
    def get(self, run_id):
        """Get detailed run log"""
        try:
            run = omics_service.get_run(run_id)
            
            state = omics_service.map_run_state(run['status'])
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
        except Exception as e:
            current_app.logger.error(f"Failed to get run {run_id}: {str(e)}")
            api.abort(500, f"Failed to get run {run_id}: {str(e)}")

@api.route('/runs/<string:run_id>/status')
class WorkflowRunStatus(Resource):
    def get(self, run_id):
        """Get run status"""
        try:
            run = omics_service.get_run(run_id)
            return {
                'run_id': run_id,
                'state': omics_service.map_run_state(run['status'])
            }
        except Exception as e:
            current_app.logger.error(f"Failed to get run status {run_id}: {str(e)}")
            api.abort(500, f"Failed to get run status {run_id}: {str(e)}")

@api.route('/runs/<string:run_id>/cancel')
class WorkflowRunCancel(Resource):
    def post(self, run_id):
        """Cancel a run"""
        try:
            omics_service.cancel_run(run_id)
            return {'run_id': run_id}
        except Exception as e:
            current_app.logger.error(f"Failed to cancel run {run_id}: {str(e)}")
            api.abort(500, f"Failed to cancel run {run_id}: {str(e)}")
