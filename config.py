"""Application Config profiles"""
import os
basedir = os.path.abspath(os.path.dirname(__file__))

class DefaultConfig: # pylint: disable=too-few-public-methods
    """Default Config profile"""

    APP_NAME = os.environ.get("APP_NAME", "FlaskApp-Skeleton")
    APP_VERSION = os.environ.get("APP_VERSION", "1.0.0")
    APP_DESCRIPTION = os.environ.get(
        "APP_DESCRIPTION", "Flask App Skeleton"
    )
    APP_AUTHOR = os.environ.get("APP_AUTHOR", "Ryan Golhar <ngsbioinformatics@gmail.com")
    DEBUG = os.environ.get("FLASK_DEBUG", False)

    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'app.db'
    )
        
class TestConfig(DefaultConfig): # pylint: disable=too-few-public-methods
    """Unit Test Config profile"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite://'
