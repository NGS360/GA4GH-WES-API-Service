from app.services.wes_provider import WesProvider

class LocalService(WesProvider):
    """Abstract base class for WES providers"""

    def start_run(self, workflow_id, role_arn, parameters=None, output_uri=None, tags=None):
        """Start a workflow run"""
        pass

    def get_run(self, run_id):
        """Get run details"""
        pass

    def list_runs(self, next_token=None, max_results=100):
        """List workflow runs"""
        pass

    def cancel_run(self, run_id):
        """Cancel a workflow run"""
        pass

    def map_run_state(self, provider_status):
        """Map provider-specific status to WES state"""
        pass