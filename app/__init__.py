'''
REST API Server
'''
from logging.config import dictConfig

from flask import Flask

from config import DefaultConfig
from app.extensions import init_extensions

from app.api import BLUEPRINT_API
from app.web import web as web_blueprint
from app.template_filters import state_to_bootstrap_class, format_datetime

# Configure (default) logging
dictConfig({
    'version': 1,
    'formatters': {'default': {
        'format': '[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
    }},
    'handlers': {'wsgi': {
        'class': 'logging.StreamHandler',
        'stream': 'ext://flask.logging.wsgi_errors_stream',
        'formatter': 'default'
    }},
    'root': {
        'level': 'INFO',
        'handlers': ['wsgi']
    }
})

def register_blueprints(app):
    ''' Register blueprints '''
    app.logger.debug("Registering blueprints")

    app.logger.debug("Registering API blueprint")
    app.register_blueprint(BLUEPRINT_API)

    app.logger.debug("Registering Web blueprint")
    app.register_blueprint(web_blueprint)

    app.logger.debug("Registered blueprints")

def create_app(config_class=DefaultConfig):
    ''' Application Factory '''
    app = Flask(__name__)

    app.config.from_object(config_class)
    app.logger.info('%s loading', app.config['APP_NAME'])
    for key, value in app.config.items():
        app.logger.info('%s: %s', key, value)

    # Initialize 3rd party extensions
    init_extensions(app)

    # Register blueprints
    register_blueprints(app)

    # Register template filters
    app.jinja_env.filters['state_to_bootstrap'] = state_to_bootstrap_class
    app.jinja_env.filters['datetime'] = format_datetime

    app.logger.info('%s loaded.', app.config['APP_NAME'])
    return app
