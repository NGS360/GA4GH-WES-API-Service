''' GA4GH WES API Workflow Execution Service Model '''
# pylint: disable=too-few-public-methods

from app.extensions import DB

class WorkflowRun(DB.Model):
    """Workflow run model"""
    __tablename__ = 'workflow_runs'

    run_id = DB.Column(DB.String(36), primary_key=True)
    state = DB.Column(DB.String(20), nullable=False)
    workflow_params = DB.Column(DB.JSON)
    workflow_type = DB.Column(DB.String(50), nullable=False)
    workflow_type_version = DB.Column(DB.String(20), nullable=False)
    workflow_engine = DB.Column(DB.String(50))
    workflow_engine_version = DB.Column(DB.String(20))
    workflow_url = DB.Column(DB.String(500), nullable=False)
    tags = DB.Column(DB.JSON)
    start_time = DB.Column(DB.DateTime)
    end_time = DB.Column(DB.DateTime)

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
