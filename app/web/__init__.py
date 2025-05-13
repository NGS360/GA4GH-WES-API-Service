''' WebUI for GA4GH WES '''
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
    runs_response = workflow_runs.get(page_size=page_size, page_token=page_token)

    # Extract runs, next_page_token, and total_runs
    runs_list = runs_response.get('runs', [])
    next_page_token = runs_response.get('next_page_token', '')
    total_runs = runs_response.get('total_runs', 0)

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

    # Calculate current page number, total pages, and run range
    try:
        current_offset = int(page_token)
        current_page = (current_offset // page_size) + 1
        total_pages = (total_runs + page_size - 1) // page_size  # Ceiling division

        # Calculate the range of runs being displayed
        start_run = current_offset + 1
        end_run = min(current_offset + page_size, total_runs)
    except ValueError:
        current_page = 1
        total_pages = (total_runs + page_size - 1) // page_size
        start_run = 1
        end_run = min(page_size, total_runs)

    return render_template('runs.html',
                          runs=runs_list,
                          next_page_token=next_page_token,
                          prev_page_token=prev_page_token,
                          page_size=page_size,
                          current_page_token=page_token,
                          total_runs=total_runs,
                          current_page=current_page,
                          total_pages=total_pages,
                          start_run=start_run,
                          end_run=end_run)

@web.route('/runs/<run_id>')
def run_detail(run_id):
    run_data = WorkflowRun().get(run_id)
    return render_template('run_detail.html', run=run_data, tasks=None)

@web.route('/runs/new', methods=['GET', 'POST'])
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
