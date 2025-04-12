'''
Main application entry point
'''
from flask import current_app
from app import create_app
from app.extensions import DB
from dotenv import load_dotenv
from sqlalchemy.sql import text

load_dotenv()
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
    application.run()
