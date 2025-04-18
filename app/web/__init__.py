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
        # List all runs from AWS HealthOmics
        runs_list = []
        next_token = None
        while True:
            response = omics_service.list_runs(next_token=next_token)
            for run in response.get('items', []):
                runs_list.append({
                    'run_id': run['id'],
                    'name': run['name'],
                    'state': omics_service.map_run_state(run['status']),
                    'start_time': run.get('startTime'),
                    'end_time': run.get('stopTime')
                })
            next_token = response.get('nextToken')
            if not next_token:
                break
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

@web.route('/run-groups')
def run_groups():
    try:
        # List all run groups from AWS HealthOmics
        groups_list = []
        next_token = None
        while True:
            response = omics_service.list_run_groups(next_token=next_token)
            for group in response.get('items', []):
                groups_list.append({
                    'group_id': group['id'],
                    'name': group.get('name', 'Unnamed Group'),
                    'description': group.get('description', ''),
                    'created_at': group.get('creationTime')
                })
            next_token = response.get('nextToken')
            if not next_token:
                break
        return render_template('run_groups.html', groups=groups_list)
    except Exception as e:
        current_app.logger.error(f"Failed to list run groups: {str(e)}")
        flash(f"Error: {str(e)}", 'error')
        return render_template('run_groups.html', groups=[])

@web.route('/run-groups/<group_id>')
def run_group_detail(group_id):
    try:
        # Get run group details
        group = omics_service.get_run_group(group_id)

        # List runs in this group
        runs_list = []
        next_token = None
        while True:
            response = omics_service.list_runs_in_group(group_id, next_token=next_token)
            for run in response.get('items', []):
                runs_list.append({
                    'run_id': run['id'],
                    'name': run.get('name', 'Unnamed Run'),
                    'state': omics_service.map_run_state(run['status']),
                    'start_time': run.get('startTime'),
                    'end_time': run.get('stopTime')
                })
            next_token = response.get('nextToken')
            if not next_token:
                break

        group_data = {
            'group_id': group_id,
            'name': group.get('name', 'Unnamed Group'),
            'description': group.get('description', ''),
            'created_at': group.get('creationTime')
        }

        return render_template('run_group_detail.html', group=group_data, runs=runs_list)
    except Exception as e:
        current_app.logger.error(f"Failed to get run group details: {str(e)}")
        flash(f"Error: {str(e)}", 'error')
        return redirect(url_for('web.run_groups'))
