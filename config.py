"""Application Config profiles"""
import os
basedir = os.path.abspath(os.path.dirname(__file__))

class DefaultConfig: # pylint: disable=too-few-public-methods
    """Default Config profile"""

    APP_NAME = os.environ.get("APP_NAME", "NGS360-GA4GH-WES-API-SERVICE")
    APP_VERSION = os.environ.get("APP_VERSION", "1.0.0")
    APP_DESCRIPTION = os.environ.get(
        "APP_DESCRIPTION", "NGS360 GA4GH WES API Service"
    )
    APP_AUTHOR = os.environ.get("APP_AUTHOR", "Ryan Golhar <ngsbioinformatics@gmail.com")
    DEBUG = os.environ.get("FLASK_DEBUG", False)

    SECRET_KEY = os.environ.get("SECRET_KEY", "changeme")

    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'app.db'
    )

    # AWS Configuration
    AWS_REGION = os.environ.get('AWS_REGION')
    AWS_OMICS_ROLE_ARN = os.environ.get('AWS_OMICS_ROLE_ARN')

class TestConfig(DefaultConfig): # pylint: disable=too-few-public-methods
    """Unit Test Config profile"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite://'
