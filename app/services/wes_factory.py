import os
from app.services.arvados import ArvadosService
from app.services.aws_omics import HealthOmicsService
from app.services.sevenbridges import SevenBridgesService
# Import other providers as they are implemented

SUPPORTED_SERVICES = {
    'Local': 'LocalService',
    'Arvados': ArvadosService,
    'Omics': HealthOmicsService,
    'SevenBridges': SevenBridgesService
}

class WesFactory:
    """Factory for creating WES provider instances"""
    @staticmethod
    def create_provider(provider_type=None):
        """
        Create a WES provider instance based on configuration.

        Args:
            provider_type: The type of provider to create.
                           If None, uses the configured default.

        Returns:
            A WesProvider instance
        """
        if provider_type is None:
            provider_type = os.getenv('DEFAULT_WES_PROVIDER', 'Local')
        if provider_type not in SUPPORTED_SERVICES:
            raise ValueError(f"Unknown provider type: {provider_type}. Supported providers are: {', '.join(SUPPORTED_SERVICES.keys())}")
        return SUPPORTED_SERVICES[provider_type]()
