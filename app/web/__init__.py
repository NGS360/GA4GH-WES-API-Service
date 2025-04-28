''' WebUI for AWS Omics Service '''
# pylint: disable=missing-function-docstring, broad-exception-caught
import json
from flask import Blueprint, render_template, redirect, url_for, request, flash, current_app
from app.api.wes import WorkflowRun, WorkflowRuns, WorkflowRunCancel

web = Blueprint('web', __name__)

@web.route('/')
def index():
    return render_template('index.html')

@web.route('/runs')
def runs():
    # Get pagination parameters from query string
    page_size = request.args.get('page_size', default=10, type=int)
    page_token = request.args.get('page_token', default='0', type=str)
    
    # List runs from the REST API with pagination
    workflow_runs = WorkflowRuns()
    runs_response = workflow_runs.get()
    
    # Check if the API supports pagination parameters
    # This is a workaround in case we're using an older version of the API
    try:
        # Try to call the get method with pagination parameters
        runs_response = workflow_runs.get(page_size=page_size, page_token=page_token)
    except TypeError:
        # If the API doesn't support pagination parameters, use the default implementation
        current_app.logger.warning("API doesn't support pagination parameters, using default implementation")
    
    # Extract runs and next_page_token
    runs_list = runs_response.get('runs', [])
    next_page_token = runs_response.get('next_page_token', '')
    
    # Calculate previous page token (if applicable)
    prev_page_token = None
    if page_token != '0':
        try:
            current_offset = int(page_token)
            if current_offset >= page_size:
                prev_page_token = str(max(0, current_offset - page_size))
        except ValueError:
            # Invalid page token, ignore
            pass
    
    return render_template('runs.html',
                          runs=runs_list,
                          next_page_token=next_page_token,
                          prev_page_token=prev_page_token,
                          page_size=page_size,
                          current_page_token=page_token)

@web.route('/runs/<run_id>')
def run_detail(run_id):
    run_data = WorkflowRun().get(run_id)
    return render_template('run_detail.html', run=run_data, tasks=None)

@web.route('/runs/new', methods=['GET'])
def new_run():
    if request.method == 'POST':
        #workflow_params = json.loads(request.form.get('workflow_params', '{}'))
        #run_id = WorkflowRuns().post(workflow_params)
        flash('Submit the run using the POST endpoint', 'error')
        #return redirect(url_for('web.run_detail', run_id=run_id))
    return render_template('new_run.html')

@web.route('/runs/<run_id>/cancel', methods=['POST'])
def cancel_run(run_id):
    WorkflowRunCancel().post(run_id)
    flash('Run cancelled successfully', 'success')
    return redirect(url_for('web.runs'))
