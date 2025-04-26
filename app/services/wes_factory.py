from app.services.aws_omics import HealthOmicsService
# Import other providers as they are implemented

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
            # Get from configuration
            from flask import current_app
            provider_type = current_app.config.get('WES_PROVIDER', 'aws-omics')
            
        if provider_type == 'aws-omics':
            return HealthOmicsService()
        # Add other providers as they are implemented
        else:
            raise ValueError(f"Unknown WES provider type: {provider_type}")
