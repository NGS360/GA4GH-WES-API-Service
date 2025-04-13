# FlaskApp-Skeleton

A Flask application skeleton that provides a solid foundation for building Flask-based REST APIs.

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
FlaskApp-Skeleton/
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

## Installation

1. Clone the repository
2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows use: venv\Scripts\activate
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
- `APP_NAME`: Application name (default: "FlaskApp-Skeleton")
- `APP_VERSION`: Application version (default: "1.0.0")
- `FLASK_DEBUG`: Debug mode flag
- `DATABASE_URL`: Database connection URL

## Running the Application

```bash
python application.py
```

The application will start on `http://localhost:5000`

### Available Endpoints

- `/healthcheck`: Application health check endpoint
- `/api/docs`: Swagger UI API documentation

## Development

### Database Migrations

```bash
flask db init    # Initialize migrations (first time only)
flask db migrate # Generate a migration
flask db upgrade # Apply migrations
```

## Author

Ryan Golhar <ngsbioinformatics@gmail.com>