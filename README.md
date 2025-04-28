# GA4GH WES API Service

GA4GH WES is designed to be 1 service = 1 backend (for cleanness and portability).

This Flask-based implementation of the GA4GH WES API Service only logs run requests to a database.
The seperate daemon monitors requests in the database and is responsible for execution on a given platform.

## Features

- Flask application factory pattern
- Blueprint-based API structure with Flask-RESTX
- SQLAlchemy database integration
- Database migrations support with Flask-Migrate
- Environment variable configuration
- Built-in health check endpoint
- API documentation with Swagger UI

## Project Structure

```
GA4GH-WES-API-Service/
├── app/
│   ├── api/           # API blueprints and endpoints
│   ├── models/        # SQLAlchemy database models
│   └── extensions.py  # Flask extensions
├── migrations/        # Database migrations
├── application.py    # Application entry point
├── config.py        # Configuration profiles
└── requirements.txt # Project dependencies
```

## Requirements

- Python 3.x
- Flask
- Flask-SQLAlchemy
- Flask-Migrate
- Flask-RESTX
- python-dotenv
- boto3

## Installation

1. Clone the repository
2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create a `.env` file with your environment variables (optional)

## Configuration

The application supports different configuration profiles:

- `DefaultConfig`: Default configuration for production
- `TestConfig`: Configuration for unit tests

Key configuration options:
- `DATABASE_URL`: Database connection URL
- `SECRET_KEY`: Secret Key used by application to secure session information

## Running the Application

```bash
python application.py
```

The application will start on `http://localhost:5000`

### Available Endpoints

- `/healthcheck`: Application health check endpoint
- `/api/docs`: Swagger UI API documentation

#### GA4GH WES API Specific Endpoint

- `/`: Index page
- `/runs`: Runs page
- `/runs/<run_id>`: Run detail page
- `/runs/new`: Create run page
- `/runs/<run_id>/cancel`: Cancel run
- `/api/ga4gh/wes/v1`: GA4GH WES REST API

## Development

### Database Migrations

```bash
flask db init    # Initialize migrations (first time only)
flask db migrate # Generate a migration
flask db upgrade # Apply migrations
```

## Author

Ryan Golhar <ngsbioinformatics@gmail.com>
