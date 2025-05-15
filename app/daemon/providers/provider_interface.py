"""
Abstract base class for workflow execution providers
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Tuple, Any

from app.models.workflow import WorkflowRun


class WorkflowProviderInterface(ABC):
    """Interface for workflow execution providers"""
    
    @abstractmethod
    def submit_workflow(self, workflow: WorkflowRun) -> str:
        """
        Submit a workflow to the provider
        
        Args:
            workflow: The workflow run to submit
            
        Returns:
            str: The provider-specific workflow ID
        """
        pass
    
    @abstractmethod
    def get_workflow_status(self, provider_id: str) -> Tuple[str, Dict[str, Any], List[Dict[str, Any]]]:
        """
        Get the status of a workflow from the provider
        
        Args:
            provider_id: The provider-specific workflow ID
            
        Returns:
            tuple: (state, outputs, task_logs)
                state: The WES state of the workflow
                outputs: Dictionary of workflow outputs
                task_logs: List of task log dictionaries
        """
        pass
    
    @abstractmethod
    def cancel_workflow(self, provider_id: str) -> bool:
        """
        Cancel a workflow
        
        Args:
            provider_id: The provider-specific workflow ID
            
        Returns:
            bool: True if cancellation was successful
        """
        pass