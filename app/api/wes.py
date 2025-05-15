''' GA4GH WES API Implementation '''
#pylint: disable=missing-module-docstring, missing-class-docstring
import datetime
import uuid
import os
from flask import request, current_app
from flask_restx import Namespace, Resource, fields
from app.models.workflow import WorkflowRun as WorkflowRunModel, TaskLog
from app.extensions import DB
from app.services.provider_factory import ServiceProviderFactory

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
    'workflow_url': fields.String(required=True),
    'service_provider': fields.String(description='Service provider to use (aws_omics, arvados, sevenbridges)')
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
        # Get available service providers
        available_providers = ServiceProviderFactory.get_available_providers()
        
        # Get system state counts
        state_counts = {}
        states = DB.session.query(WorkflowRunModel.state, DB.func.count(WorkflowRunModel.run_id)) \
            .group_by(WorkflowRunModel.state).all()
        for state, count in states:
            state_counts[state] = count
        
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
            'system_state_counts': state_counts,
            'auth_instructions_url': 'https://example.com/auth',
            'tags': {
                'available_service_providers': available_providers
            }
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
            WorkflowRunModel.start_time.desc()).limit(page_size + 1).offset(offset).all()

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
        run_id = str(uuid.uuid4())
        
        # Get service provider from request or use default
        service_provider = api.payload.get('service_provider')
        if not service_provider:
            service_provider = os.environ.get('DEFAULT_SERVICE_PROVIDER', 'aws_omics')
        
        # Create the workflow run record
        new_run = WorkflowRunModel(
            run_id=run_id,
            state='QUEUED',
            workflow_type=api.payload['workflow_type'],
            workflow_type_version=api.payload['workflow_type_version'],
            workflow_url=api.payload['workflow_url'],
            workflow_params=api.payload.get('workflow_params', {}),
            workflow_engine=api.payload.get('workflow_engine'),
            workflow_engine_version=api.payload.get('workflow_engine_version'),
            tags=api.payload.get('tags', {}),
            start_time=datetime.datetime.now(datetime.UTC),
            service_provider=service_provider
        )
        
        # Save the initial record
        DB.session.add(new_run)
        DB.session.commit()
        
        try:
            # Get the appropriate service provider
            provider = ServiceProviderFactory.create_provider(service_provider)
            
            # Submit the workflow to the provider
            result = provider.submit_workflow(new_run)
            
            # Update the workflow run with provider information
            new_run.provider_run_id = result['provider_run_id']
            new_run.provider_status = result['status']
            new_run.provider_metadata = result.get('metadata', {})
            new_run.state = provider.map_status_to_wes(result['status'])
            
            DB.session.commit()
            
            current_app.logger.info(f"Workflow submitted to {service_provider}: {run_id}")
            
        except Exception as e:
            # If submission fails, update the state to reflect the error
            new_run.state = 'SYSTEM_ERROR'
            new_run.provider_metadata = {'error': str(e)}
            DB.session.commit()
            
            current_app.logger.error(f"Error submitting workflow to {service_provider}: {str(e)}")
            
            # We don't re-raise the exception because we want to return the run_id
            # even if submission fails, so the client can check the status later
        
        return {'run_id': run_id}

@api.route('/runs/<string:run_id>')
class WorkflowRun(Resource):
    def get(self, run_id):
        """Get detailed run log"""
        run = DB.session.query(WorkflowRunModel).filter_by(run_id=run_id).first()
        if not run:
            return {'error': 'Run not found'}, 404
        
        # If the run has a service provider and provider_run_id, get the latest status
        if run.service_provider and run.provider_run_id:
            try:
                provider = ServiceProviderFactory.create_provider(run.service_provider)
                result = provider.get_run_status(run)
                
                # Update the run status in the database
                run.provider_status = result['status']
                run.state = provider.map_status_to_wes(result['status'])
                run.provider_metadata = result.get('metadata', run.provider_metadata)
                
                # If the run is complete, update the end time if not already set
                if run.state in ['COMPLETE', 'EXECUTOR_ERROR', 'SYSTEM_ERROR', 'CANCELED']:
                    if not run.end_time:
                        run.end_time = datetime.datetime.now(datetime.UTC)
                
                DB.session.commit()
            except Exception as e:
                current_app.logger.error(f"Error getting run status from provider: {str(e)}")
                # Don't update the state if there's an error getting the status
        
        tasks = DB.session.query(TaskLog).filter_by(run_id=run_id).all()
        
        # Get outputs from provider metadata if available
        outputs = {}
        if run.provider_metadata and 'outputs' in run.provider_metadata:
            outputs = run.provider_metadata['outputs']
        
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
            'outputs': outputs,
            'request': {
                'workflow_type': run.workflow_type,
                'workflow_type_version': run.workflow_type_version,
                'workflow_url': run.workflow_url,
                'workflow_params': run.workflow_params,
                'workflow_engine': run.workflow_engine,
                'workflow_engine_version': run.workflow_engine_version,
                'tags': run.tags,
                'service_provider': run.service_provider
            }
        }

@api.route('/runs/<string:run_id>/status')
class WorkflowRunStatus(Resource):
    def get(self, run_id):
        """Get run status"""
        run = DB.session.query(WorkflowRunModel).filter_by(run_id=run_id).first()
        if not run:
            return {'error': 'Run not found'}, 404
        
        # If the run has a service provider and provider_run_id, get the latest status
        if run.service_provider and run.provider_run_id:
            try:
                provider = ServiceProviderFactory.create_provider(run.service_provider)
                result = provider.get_run_status(run)
                
                # Update the run status in the database
                run.provider_status = result['status']
                run.state = provider.map_status_to_wes(result['status'])
                
                # If the run is complete, update the end time if not already set
                if run.state in ['COMPLETE', 'EXECUTOR_ERROR', 'SYSTEM_ERROR', 'CANCELED']:
                    if not run.end_time:
                        run.end_time = datetime.datetime.now(datetime.UTC)
                
                DB.session.commit()
            except Exception as e:
                current_app.logger.error(f"Error getting run status from provider: {str(e)}")
                # Don't update the state if there's an error getting the status
        
        return {
            'run_id': run.run_id,
            'state': run.state
        }

@api.route('/runs/<string:run_id>/cancel')
class WorkflowRunCancel(Resource):
    def post(self, run_id):
        """Cancel a run"""
        run = DB.session.query(WorkflowRunModel).filter_by(run_id=run_id).first()
        if not run:
            return {'error': 'Run not found'}, 404
        
        # If the run has a service provider and provider_run_id, cancel it through the provider
        if run.service_provider and run.provider_run_id:
            try:
                provider = ServiceProviderFactory.create_provider(run.service_provider)
                provider.cancel_run(run)
                
                # Update the state to CANCELING
                run.state = 'CANCELING'
                DB.session.commit()
                
                current_app.logger.info(f"Cancellation request sent for run {run_id}")
            except Exception as e:
                current_app.logger.error(f"Error canceling run through provider: {str(e)}")
                # Set the state to CANCELED even if the provider call fails
                run.state = 'CANCELED'
                DB.session.commit()
        else:
            # If no provider is associated, just mark it as canceled
            run.state = 'CANCELED'
            DB.session.commit()
        
        return {'run_id': run_id}
