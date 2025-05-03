NAME=ga4gh_wes_api_service

build:
	pylint --rcfile=.pylintrc *.py app/ tests/
	docker build -t $(NAME) .

run:
	# This target is just to run the apiserver application and assumes all other
	# required resources (mysql) are running. Use launch-stack target instead
	docker run -ti --rm -p 5000:5000 -e FLASK_APP=application.py -e FLASK_ENV=development --name $(NAME) $(NAME)

test:	# This target is basically the same as the Github Action Workflow to lint and unit test locally
	pylint --rcfile=.pylintrc *.py app/ #tests/
	coverage run -m pytest
	coverage html && open htmlcov/index.html

