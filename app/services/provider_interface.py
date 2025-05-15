"""Service Provider Interface for Workflow Execution"""
from abc import ABC, abstractmethod

class WorkflowServiceProvider(ABC):
    """Abstract base class for workflow service providers"""
    
    @abstractmethod
    def submit_workflow(self, workflow_run):
        """
        Submit a workflow to the service provider
        
        Args:
            workflow_run: The WorkflowRun model instance
            
        Returns:
            dict: Provider-specific response with at least:
                - provider_run_id: ID of the run in the provider's system
                - status: Initial status of the run
        """
        pass
    
    @abstractmethod
    def get_run_status(self, workflow_run):
        """
        Get the status of a workflow run
        
        Args:
            workflow_run: The WorkflowRun model instance
            
        Returns:
            dict: Provider-specific response with at least:
                - status: Current status of the run
                - outputs: Any outputs from the run (if available)
        """
        pass
    
    @abstractmethod
    def cancel_run(self, workflow_run):
        """
        Cancel a workflow run
        
        Args:
            workflow_run: The WorkflowRun model instance
            
        Returns:
            bool: True if cancellation was successful
        """
        pass
    
    @abstractmethod
    def map_status_to_wes(self, provider_status):
        """
        Map provider-specific status to WES status
        
        Args:
            provider_status: Provider-specific status string
            
        Returns:
            str: WES status string
        """
        pass