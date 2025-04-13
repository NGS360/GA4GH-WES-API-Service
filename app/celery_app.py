'''
Background task manager for the application.
Since AWS HealthOmics can only store a limited number of workflow runs,
we need to periodically sync completed workflow runs from AWS HealthOmics to the database
'''
from celery import Celery
from celery.schedules import crontab

def create_celery_app(app):
    ''' Create a new Celery app instance and configure it with the Flask app's settings. '''
    celery = Celery(
        app.import_name,
        broker=app.config['CELERY_BROKER_URL']
    )

    celery.conf.beat_schedule = {
        'sync-completed-workflows': {
            'task': 'app.tasks.workflow_tasks.sync_completed_workflows',
            'schedule': crontab(minute='*/15')  # Run every 15 minutes
        }
    }

    return celery
