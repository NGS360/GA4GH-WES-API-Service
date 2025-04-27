''' GA4GH WES API Implementation '''
#pylint: disable=missing-module-docstring, missing-class-docstring
import datetime
import uuid
from flask_restx import Namespace, Resource, fields
from app.models.workflow import WorkflowRun as WorkflowRunModel, TaskLog
from app.extensions import DB

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
                'CWL': {'workflow_type_version': ['v1.0']},
                'WDL': {'workflow_type_version': ['1.0']}
            },
            'supported_wes_versions': ['1.0.0'],
            'supported_filesystem_protocols': ['file', 'http', 'https'],
            'workflow_engine_versions': {
                'cwltool': '3.1.20230906242',
                'cromwell': '84'
            },
            'default_workflow_engine_parameters': [],
            'system_state_counts': {},
            'auth_instructions_url': 'https://example.com/auth',
            'tags': {}
        }

@api.route('/runs')
class WorkflowRuns(Resource):
    @api.doc('list_runs')
    def get(self):
        """List workflow runs"""
        runs = WorkflowRunModel.query.all()
        return {
            'runs': [{
                'run_id': run.run_id,
                'state': run.state
            } for run in runs],
            'next_page_token': ''
        }

    @api.doc('run_workflow')
    @api.expect(run_request)
    def post(self):
        """Run a workflow"""
        run_id = str(uuid.uuid4())
        new_run = WorkflowRunModel(
            run_id=run_id,
            state='QUEUED',
            workflow_type=api.payload['workflow_type'],
            workflow_type_version=api.payload['workflow_type_version'],
            workflow_url=api.payload['workflow_url'],
            workflow_params=api.payload.get('workflow_params'),
            workflow_engine=api.payload.get('workflow_engine'),
            workflow_engine_version=api.payload.get('workflow_engine_version'),
            tags=api.payload.get('tags'),
            start_time=datetime.datetime.now(datetime.UTC)
        )
        DB.session.add(new_run)
        DB.session.commit()
        return {'run_id': run_id}

@api.route('/runs/<string:run_id>')
class WorkflowRun(Resource):
    def get(self, run_id):
        """Get detailed run log"""
        run = DB.session.query(WorkflowRunModel).filter_by(run_id=run_id).first()
        if not run:
            return {'error': 'Run not found'}, 404
        tasks = DB.session.query(TaskLog).filter_by(run_id=run_id).all()

        return {
            'run_id': run.run_id,
            'state': run.state,
            'run_log': {
                'name': 'workflow',
                'start_time': run.start_time.isoformat() if run.start_time else None,
                'end_time': run.end_time.isoformat() if run.end_time else None
            },
            'task_logs': [{
                'name': task.name,
                'cmd': task.cmd,
                'start_time': task.start_time.isoformat() if task.start_time else None,
                'end_time': task.end_time.isoformat() if task.end_time else None,
                'stdout': task.stdout,
                'stderr': task.stderr,
                'exit_code': task.exit_code
            } for task in tasks],
            'outputs': {}
        }

@api.route('/runs/<string:run_id>/status')
class WorkflowRunStatus(Resource):
    def get(self, run_id):
        """Get run status"""
        run = DB.session.query(WorkflowRunModel).filter_by(run_id=run_id).first()
        return {
            'run_id': run.run_id,
            'state': run.state
        }

@api.route('/runs/<string:run_id>/cancel')
class WorkflowRunCancel(Resource):
    def post(self, run_id):
        """Cancel a run"""
        run = DB.session.query(WorkflowRunModel).filter_by(run_id=run_id).first()
        run.state = 'CANCELED'
        DB.session.commit()
        return {'run_id': run_id}
