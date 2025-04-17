''' GA4GH WES API Workflow Execution Service Model '''
# pylint: disable=too-few-public-methods

from app.extensions import DB

class WorkflowRun(DB.Model):
    """Workflow run model"""
    __tablename__ = 'workflow_runs'

    run_id = DB.Column(DB.String(36), primary_key=True)
    name = DB.Column(DB.String(200), nullable=False)
    state = DB.Column(DB.String(20), nullable=False)
    workflow_params = DB.Column(DB.JSON)
    workflow_type = DB.Column(DB.String(50), nullable=False)
    workflow_type_version = DB.Column(DB.String(20), nullable=False)
    workflow_engine = DB.Column(DB.String(50))
    workflow_engine_version = DB.Column(DB.String(20))
    workflow_url = DB.Column(DB.String(500), nullable=False)
    tags = DB.Column(DB.JSON)

    # AWS Omics specific fields
    arn = DB.Column(DB.String(255))
    workflow_id = DB.Column(DB.String(36))
    priority = DB.Column(DB.Integer)
    storage_capacity = DB.Column(DB.Integer)
    creation_time = DB.Column(DB.DateTime)
    start_time = DB.Column(DB.DateTime)
    stop_time = DB.Column(DB.DateTime)
    storage_type = DB.Column(DB.String(50))

class TaskLog(DB.Model):
    """Task log model"""
    __tablename__ = 'task_logs'

    id = DB.Column(DB.String(36), primary_key=True)
    run_id = DB.Column(DB.String(36), DB.ForeignKey('workflow_runs.run_id'))
    name = DB.Column(DB.String(200), nullable=False)
    cmd = DB.Column(DB.JSON)  # Array of strings
    start_time = DB.Column(DB.DateTime)
    end_time = DB.Column(DB.DateTime)
    stdout = DB.Column(DB.String(500))  # URL to stdout logs
    stderr = DB.Column(DB.String(500))  # URL to stderr logs
    exit_code = DB.Column(DB.Integer)
    system_logs = DB.Column(DB.JSON)  # Array of strings
