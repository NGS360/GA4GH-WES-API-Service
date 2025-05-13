import unittest
import datetime
import uuid
from app import create_app
from app.extensions import DB
from app.models.workflow import WorkflowRun
from config import TestConfig

class BaseTestCase(unittest.TestCase):
    """Base test case for all tests"""
    
    def setUp(self):
        """Set up test environment"""
        self.app = create_app(TestConfig)

        # Create the database and load test data
        self.app_context = self.app.app_context()
        self.app_context.push()

        DB.create_all()

        self.client = self.app.test_client()

    def create_test_runs(self, count=50):
        """Create test workflow runs in the database"""
        # Create test runs
        states = ['QUEUED', 'INITIALIZING', 'RUNNING', 'COMPLETE', 'EXECUTOR_ERROR', 'SYSTEM_ERROR', 'CANCELED']
        workflow_types = ['CWL', 'WDL']

        for i in range(count):
            # Calculate dates with some variation
            start_time = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=i % 30, hours=i % 24)

            # Some runs are completed, some are still running
            end_time = None
            state = states[i % len(states)]
            if state in ['COMPLETE', 'EXECUTOR_ERROR', 'SYSTEM_ERROR', 'CANCELED']:
                end_time = start_time + datetime.timedelta(hours=2, minutes=(i % 60))

            # Create run with unique ID
            run_id = str(uuid.uuid4())
            workflow_type = workflow_types[i % len(workflow_types)]

            new_run = WorkflowRun(
                run_id=run_id,
                state=state,
                workflow_type=workflow_type,
                workflow_type_version='1.0',
                workflow_url=f'https://example.com/workflows/workflow_{i}.{workflow_type.lower()}',
                workflow_params={'input': f'test_input_{i}'},
                workflow_engine='test_engine',
                workflow_engine_version='1.0',
                tags={'test': 'true', 'index': i},
                start_time=start_time,
                end_time=end_time
            )

            DB.session.add(new_run)

        # Commit all runs
        DB.session.commit()

    def tearDown(self):
        """Clean up after test"""
        # Close and remove the temporary database
        self.client = None

        DB.drop_all()
        DB.session.remove()

        self.app_context.pop()

        self.app = None
