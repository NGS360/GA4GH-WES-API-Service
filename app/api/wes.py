''' GA4GH WES API Implementation '''
#pylint: disable=missing-module-docstring, missing-class-docstring
import uuid
from flask import request
from flask_restx import Namespace, Resource, fields
from app.models.workflow import WorkflowRun as WorkflowRunModel, TaskLog
from app.extensions import DB

# Create namespace
api = Namespace('ga4gh/wes/v1', description='Workflow Execution Service API')

# Define API models
# For now, define the supported engines here. This should come from a database or config file in the future.
supported_engines = {
    'cwltool': '3.1.20230906242',
    'Arvados': '3.0.0',
    'SevenBridges': '1.0.0',
    'AWSHealthOmics': '1.0.0'
}

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
                'CWL': {'workflow_type_version': ['v1.0', 'v1.1', 'v1.2']},
            },
            'supported_wes_versions': ['1.0.0'],
            'supported_filesystem_protocols': ['file', 'http', 'https'],
            'workflow_engine_versions': supported_engines,
            'default_workflow_engine_parameters': [],
            'system_state_counts': {},
            'auth_instructions_url': 'https://example.com/auth',
            'tags': {}
        }

@api.route('/runs')
class WorkflowRuns(Resource):
    @api.doc('list_runs', params={
        'page_size': 'OPTIONAL: The preferred number of workflow runs to return in a page.',
        'page_token': 'OPTIONAL: Token to use to indicate where to start getting results.'
    })
    def get(self, page_size=None, page_token=None):
        """List workflow runs"""
        # Parse pagination parameters from request args if not provided directly
        if page_size is None:
            page_size = request.args.get('page_size', type=int, default=50)
        if page_token is None:
            page_token = request.args.get('page_token', type=str, default='0')

        try:
            # Convert page_token to offset
            offset = int(page_token)
        except ValueError:
            # Handle invalid page_token
            return {'msg': 'Invalid page_token', 'status_code': 400}, 400

        # Query with pagination
        runs = WorkflowRunModel.query.order_by(
            WorkflowRunModel.submitted_at.desc()).limit(page_size + 1).offset(offset).all()

        # Check if there are more results
        has_next_page = len(runs) > page_size
        if has_next_page:
            runs = runs[:-1]  # Remove the extra item we fetched

        # Generate next_page_token
        next_page_token = str(offset + page_size) if has_next_page else ''

        # Get total count of runs
        total_runs = WorkflowRunModel.query.count()

        # Format response using RunSummary format
        return {
            'runs': [{
                'run_id': run.run_id,
                'state': run.state,
                'submitted_at': run.submitted_at.isoformat() if run.submitted_at else None,
                'start_time': run.start_time.isoformat() if run.start_time else None,
                'end_time': run.end_time.isoformat() if run.end_time else None,
                'tags': run.tags or {}
            } for run in runs],
            'next_page_token': next_page_token,
            'total_runs': total_runs
        }

    @api.doc('run_workflow')
    @api.expect(run_request)
    def post(self):
        """Run a workflow"""
        if api.payload.get('workflow_engine') is None:
            return {'error': 'Workflow engine not specified'}, 400
        if api.payload['workflow_engine'] not in supported_engines:
            return {'error': f"Unsupported workflow engine: {api.payload['workflow_engine']}"}, 400
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
            #start_time=datetime.datetime.now(datetime.timezone.utc)
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
            'submitted_at': run.submitted_at.isoformat() if run.submitted_at else None,
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
