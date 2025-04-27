from abc import ABC, abstractmethod

class WesProvider(ABC):
    """Abstract base class for WES providers"""

    @abstractmethod
    def start_run(self, workflow_id, parameters=None, output_uri=None, tags=None):
        """Start a workflow run"""
        pass

    @abstractmethod
    def get_run(self, run_id):
        """Get run details"""
        pass

    @abstractmethod
    def list_runs(self, next_token=None, max_results=100):
        """List workflow runs"""
        pass

    @abstractmethod
    def cancel_run(self, run_id):
        """Cancel a workflow run"""
        pass

    @abstractmethod
    def map_run_state(self, provider_status):
        """Map provider-specific status to WES state"""
        pass