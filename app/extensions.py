'''
Initialize Flask (3rd party) Extensions
'''
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

DB = SQLAlchemy()
MIGRATE = Migrate()

def init_extensions(app):
    ''' Initialize Flask Extensions '''
    app.logger.debug("Initializing extensions")

    app.logger.debug("Initializing SQLAlchemy")
    DB.init_app(app)
    app.logger.debug("Initializing Flask-Migrate")
    MIGRATE.init_app(app, DB)

    app.logger.debug("Initialized extensions")
