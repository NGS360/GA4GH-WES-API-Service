'''
REST API
'''
from flask import Blueprint
from flask_restx import Api
from .wes import api as wes_api

BLUEPRINT_API = Blueprint('api', __name__, url_prefix='')
API = Api(BLUEPRINT_API,
          title='GA4GH WES API',
          version='1.0',
          description='GA4GH Workflow Execution Service API',
          doc='/docs')

API.add_namespace(wes_api)
