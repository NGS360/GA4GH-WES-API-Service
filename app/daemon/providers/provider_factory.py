"""
Factory for creating workflow providers
"""
import logging
from typing import Dict, Type

from .provider_interface import WorkflowProviderInterface
from .sevenbridges import SevenBridgesProvider
from .healthomics import HealthOmicsProvider
from .arvados import ArvadosProvider


class ProviderFactory:
    """Factory for creating workflow providers"""
    
    # Registry of provider types to provider classes
    _providers: Dict[str, Type[WorkflowProviderInterface]] = {
        'sevenbridges': SevenBridgesProvider,
        'healthomics': HealthOmicsProvider,
        'arvados': ArvadosProvider,
    }
    
    # Cache of provider instances
    _instances = {}
    
    @classmethod
    def register_provider(cls, provider_type: str, provider_class: Type[WorkflowProviderInterface]) -> None:
        """
        Register a new provider type
        
        Args:
            provider_type: The type name of the provider
            provider_class: The provider class
        """
        cls._providers[provider_type] = provider_class
    
    @classmethod
    def get_provider(cls, provider_type: str) -> WorkflowProviderInterface:
        """
        Get a workflow provider by type
        
        Args:
            provider_type: The type of provider to create
            
        Returns:
            WorkflowProviderInterface: The provider instance
            
        Raises:
            ValueError: If the provider type is not supported
        """
        logger = logging.getLogger(__name__)
        
        # Check if the provider type is supported
        if provider_type not in cls._providers:
            supported = ", ".join(cls._providers.keys())
            raise ValueError(
                f"Unsupported provider type: {provider_type}. "
                f"Supported types are: {supported}"
            )
        
        # Check if we already have an instance of this provider
        if provider_type not in cls._instances:
            logger.info(f"Creating new provider instance for {provider_type}")
            provider_class = cls._providers[provider_type]
            try:
                cls._instances[provider_type] = provider_class()
            except Exception as e:
                logger.error(f"Error creating provider {provider_type}: {e}")
                raise
        
        return cls._instances[provider_type]
    
    @classmethod
    def get_available_providers(cls) -> Dict[str, str]:
        """
        Get a dictionary of available provider types and their descriptions
        
        Returns:
            Dict[str, str]: Dictionary of provider types to descriptions
        """
        return {
            'sevenbridges': 'SevenBridges/Velsera',
            'healthomics': 'AWS HealthOmics',
            'arvados': 'Arvados',
        }