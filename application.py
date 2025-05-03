'''
Main application entry point
'''
import os

# pylint: disable=wrong-import-position
# Environment variables are loaded from .env file first,
# before DefaultConfig is loaded or else DefaultConfig will not see
# the environment variables set in .env file.
from dotenv import load_dotenv
load_dotenv()
# pylint: enable=wrong-import-position

from flask import current_app
from sqlalchemy.sql import text

from app import create_app
from app.extensions import DB

application = create_app()

@application.route('/healthcheck')
def healthcheck():
    ''' Healthcheck endpoint '''
    try:
        current_app.logger.debug('Checking database connection')
        DB.session.query(text('1')).from_statement(text('SELECT 1')).all()
        current_app.logger.debug('Checking database connection...OK')
        return '<h1>It works.</h1>'
    except Exception as e: # pylint: disable=broad-exception-caught
        # e holds description of the error
        current_app.logger.debug('Checking database connection...FAILED')
        current_app.logger.error('Error: %s', e)
        error_text = "<p>The error:<br>" + str(e) + "</p>"
        hed = '<h1>Something is broken.</h1>'
        return hed + error_text

# Run the application
if __name__ == "__main__":
    # host should be 0.0.0.0 when running in a Docker container
    # but not when run in ElasticBeanStalk
    host = os.environ.get('FLASK_RUN_HOST', '127.0.0.1')
    port = os.environ.get('FLASK_RUN_PORT', '5000')
    application.logger.info('Starting %s on %s:%s', application.config['APP_NAME'], host, port)
    application.run(host=host, port=int(port))
