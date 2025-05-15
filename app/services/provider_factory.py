"""Service Provider Factory"""
from app.services.aws_omics_provider import AwsOmicsProvider
from app.services.arvados_provider import ArvadosProvider
from app.services.sevenbridges_provider import SevenBridgesProvider

class ServiceProviderFactory:
    """Factory for creating service provider instances"""
    
    @staticmethod
    def create_provider(provider_name):
        """
        Create a service provider instance based on the provider name
        
        Args:
            provider_name: Name of the service provider
            
        Returns:
            WorkflowServiceProvider: An instance of the requested service provider
            
        Raises:
            ValueError: If the provider is not supported
        """
        if provider_name == 'aws_omics':
            return AwsOmicsProvider()
        elif provider_name == 'arvados':
            return ArvadosProvider()
        elif provider_name == 'sevenbridges':
            return SevenBridgesProvider()
        else:
            raise ValueError(f"Unsupported service provider: {provider_name}")
    
    @staticmethod
    def get_available_providers():
        """
        Get a list of available service providers
        
        Returns:
            list: List of available provider names
        """
        return ['aws_omics', 'arvados', 'sevenbridges']