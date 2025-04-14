''' WebUI for AWS Omics Service '''
# pylint: disable=missing-function-docstring, broad-exception-caught
import json
from flask import Blueprint, render_template, redirect, url_for, request, flash, current_app
from app.services.aws_omics import HealthOmicsService

web = Blueprint('web', __name__)
omics_service = HealthOmicsService()

@web.route('/')
def index():
    return render_template('index.html')

@web.route('/runs')
def runs():
    try:
        response = omics_service.list_runs()
        runs_list = []
        for run in response.get('items', []):
            runs_list.append({
                'run_id': run['id'],
                'name': run['name'],
                'state': omics_service.map_run_state(run['status']),
                'start_time': run.get('startTime'),
                'end_time': run.get('stopTime')
            })
        return render_template('runs.html', runs=runs_list)
    except Exception as e:
        current_app.logger.error(f"Failed to list runs: {str(e)}")
        flash(f"Error: {str(e)}", 'error')
        return render_template('runs.html', runs=[])

@web.route('/runs/<run_id>')
def run_detail(run_id):
    try:
        run = omics_service.get_run(run_id)
        state = omics_service.map_run_state(run['status'])

        run_data = {
            'run_id': run_id,
            'state': state,
            'run_log': {
                'name': run.get('name', 'workflow'),
                'start_time': run.get('startTime'),
                'end_time': run.get('stopTime'),
                'stdout': run.get('outputUri'),
                'stderr': run.get('logStream')
            }
        }

        tasks = []
        for task in run.get('logStream', {}).get('tasks', []):
            tasks.append({
                'id': task.get('taskId'),
                'name': task.get('name'),
                'start_time': task.get('startTime'),
                'end_time': task.get('stopTime'),
                'exit_code': task.get('exitCode'),
                'stdout': f"s3://{run['outputUri']}/logs/{task['taskId']}/stdout.log",
                'stderr': f"s3://{run['outputUri']}/logs/{task['taskId']}/stderr.log"
            })

        return render_template('run_detail.html', run=run_data, tasks=tasks)
    except Exception as e:
        current_app.logger.error(f"Failed to get run details: {str(e)}")
        flash(f"Error: {str(e)}", 'error')
        return redirect(url_for('web.runs'))

@web.route('/runs/new', methods=['GET', 'POST'])
def new_run():
    if request.method == 'POST':
        try:
            workflow_params = json.loads(request.form.get('workflow_params', '{}'))
            run_id = omics_service.start_run(
                workflow_id=request.form['workflow_url'],
                role_arn=current_app.config['AWS_OMICS_ROLE_ARN'],
                parameters=workflow_params
            )
            flash(f'Workflow run started with ID: {run_id}', 'success')
            return redirect(url_for('web.run_detail', run_id=run_id))
        except Exception as e:
            current_app.logger.error(f"Failed to start run: {str(e)}")
            flash(f"Error: {str(e)}", 'error')
            return render_template('new_run.html')
    return render_template('new_run.html')

@web.route('/runs/<run_id>/cancel', methods=['POST'])
def cancel_run(run_id):
    try:
        omics_service.cancel_run(run_id)
        flash('Run cancelled successfully', 'success')
    except Exception as e:
        current_app.logger.error(f"Failed to cancel run: {str(e)}")
        flash(f"Error: {str(e)}", 'error')
    return redirect(url_for('web.runs'))
