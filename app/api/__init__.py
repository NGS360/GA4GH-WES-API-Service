'''
REST API
'''
from flask import Blueprint
from flask_restx import Api

# Import the projects namespace
#from .projects import NS as projects_ns

BLUEPRINT_API = Blueprint('api', __name__, url_prefix='/api')
API = Api(BLUEPRINT_API,
            title='NGS360 API',
            version='1.0',
            description='NGS360 REST API',
            doc='/docs')

#API.add_namespace(projects_ns)
