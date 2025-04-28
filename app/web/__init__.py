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
    # List all the runs from the REST API
    runs_list = WorkflowRuns().get()
    return render_template('runs.html', runs=runs_list)

@web.route('/runs/<run_id>')
def run_detail(run_id):
    run_data = WorkflowRun().get(run_id)
    return render_template('run_detail.html', run=run_data, tasks=None)

@web.route('/runs/new', methods=['GET'])
def new_run():
    if request.method == 'POST':
        #workflow_params = json.loads(request.form.get('workflow_params', '{}'))
        #run_id = WorkflowRuns().post(workflow_params)
        flash(f'Submit the run using the POST endpoint', 'error')
        #return redirect(url_for('web.run_detail', run_id=run_id))
    return render_template('new_run.html')

@web.route('/runs/<run_id>/cancel', methods=['POST'])
def cancel_run(run_id):
    WorkflowRunCancel().post(run_id)
    flash('Run cancelled successfully', 'success')
    return redirect(url_for('web.runs'))
