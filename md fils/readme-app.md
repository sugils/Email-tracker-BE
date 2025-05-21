# app.py - Detailed Documentation

## Overview

`app.py` serves as the main entry point for the Email Campaign Management API. It initializes the Flask application, sets up middleware, configures authentication, registers routes, and starts the scheduler for background tasks. This file follows the principle of keeping the route definitions clean by delegating business logic to controllers.

## Imports

```python
from flask import Flask, request, jsonify, g
from flask_cors import CORS
from flask_jwt_extended import JWTManager, jwt_required, create_access_token, get_jwt_identity
import os
import secrets
from datetime import timedelta
from threading import Thread
from apscheduler.schedulers.background import BackgroundScheduler
import atexit
import logging
```

- **Flask**: Web framework to create the API
- **CORS**: Cross-Origin Resource Sharing support for the API
- **JWTManager**: Handles JSON Web Token authentication
- **os**: Used to access environment variables
- **secrets**: Provides cryptographically strong random values for JWT secret key
- **timedelta**: Used to set JWT expiration time
- **Thread**: Used for running email sending in background
- **BackgroundScheduler**: Scheduled task execution for reply checking
- **atexit**: Registers shutdown function for the scheduler
- **logging**: Configures application logging

```python
# Import controllers
from controller import (
    auth_controller, 
    campaign_controller, 
    recipient_controller, 
    template_controller,
    tracking_controller,
    debug_controller
)

# Import helpers
from helper import get_db_connection, close_db_connection, safe_check_for_replies
```

These lines import the controller instances and helper functions from their respective modules.

## Configuration

```python
# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
)
```

Sets up application logging with timestamps, log levels, and module names for better debugging.

```python
# Initialize Flask app
app = Flask(__name__)

# Configure CORS to allow cross-origin requests
CORS(app, 
     resources={r"/*": {"origins": "*"}},
     supports_credentials=True,
     allow_headers=["Content-Type", "Authorization", "X-Requested-With", "Accept", "Origin"],
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
     expose_headers=["Content-Type", "Authorization"])
```

Creates the Flask application instance and configures CORS to allow API access from different origins (domains). This is essential for web applications that make API calls from a browser.

```python
# Generate a secret key for JWT tokens
generated_key = secrets.token_hex(32)

# JWT Configuration
app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY', generated_key)
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=1)

app.logger.info(f"Using JWT secret key: {app.config['JWT_SECRET_KEY'][:8]}...") # Show first 8 chars for debugging

# Initialize the JWT manager
jwt = JWTManager(app)
```

Sets up JWT authentication:
1. Generates a random secret key if not provided in environment variables
2. Sets token expiration to 1 hour
3. Logs the first 8 characters of the secret key for debugging
4. Initializes the JWT manager with the Flask app

## Database Connection Management

```python
# Clean up the database connection at the end of each request
@app.teardown_appcontext
def teardown_db(exception):
    close_db_connection(exception)
```

This function runs at the end of each request to close database connections, preventing connection leaks.

## Background Tasks Setup

```python
# Initialize scheduler for checking replies - runs every minute
scheduler = BackgroundScheduler()
scheduler.add_job(func=safe_check_for_replies, trigger="interval", minutes=1)
scheduler.start()

# Shut down the scheduler when exiting the app
atexit.register(lambda: scheduler.shutdown())
```

Sets up a background scheduler to:
1. Run the `safe_check_for_replies` function every minute to check for email replies
2. Register an exit handler to shut down the scheduler when the application exits

## Request Logging

```python
# Request logging middleware
@app.before_request
def log_request_info():
    if app.debug:
        app.logger.debug('Headers: %s', request.headers)
        app.logger.debug('Body: %s', request.get_data())

@app.after_request
def log_response_info(response):
    if app.debug and response.content_type == 'application/json':
        app.logger.debug('Response: %s', response.get_data())
    return response
```

These middleware functions log request headers, bodies, and responses when in debug mode, making it easier to trace API calls during development.

## Error Handlers

```python
# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({
        'status': 'error',
        'message': 'The requested URL was not found on the server.'
    }), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        'status': 'error',
        'message': 'An internal server error occurred.',
        'details': str(error) if app.debug else None
    }), 500
```

Defines custom error handlers for 404 (Not Found) and 500 (Internal Server Error) responses, returning JSON instead of HTML for API consistency.

## Database Initialization

```python
# Initialize database on app startup
with app.app_context():
    from models import init_db
    init_db()
```

Imports and runs the `init_db` function from the models module to create database tables if they don't exist.

## Routes

The rest of the file defines the API routes. Let's examine some key routes:

### Authentication Routes

```python
@app.route('/api/register', methods=['POST'])
def register():
    """Register a new user"""
    data = request.get_json()
    return auth_controller.register_user(data)

@app.route('/api/login', methods=['POST'])
def login():
    """Login user and return JWT token"""
    data = request.get_json()
    return auth_controller.login_user(data)
```

These routes handle user registration and authentication:
1. Extract JSON data from request
2. Pass data to the auth controller for processing
3. Return the controller's response

### Campaign Routes

```python
@app.route('/api/campaigns', methods=['GET'])
@jwt_required()
def get_campaigns():
    """Get all campaigns for current user"""
    user_id = get_jwt_identity()
    return campaign_controller.get_all_campaigns(user_id)

@app.route('/api/campaigns', methods=['POST'])
@jwt_required()
def create_campaign():
    """Create a new campaign"""
    user_id = get_jwt_identity()
    data = request.get_json()
    return campaign_controller.create_new_campaign(user_id, data)
```

These routes handle campaign management:
1. `@jwt_required()` ensures the user is authenticated
2. `get_jwt_identity()` extracts the user ID from the JWT token
3. Pass user ID and request data to the campaign controller
4. Return the controller's response

### Email Sending Route

```python
@app.route('/api/campaigns/<campaign_id>/send', methods=['POST'])
@jwt_required()
def send_campaign(campaign_id):
    """Send a campaign or test email"""
    user_id = get_jwt_identity()
    data = request.get_json() or {'test_mode': False}
    test_mode = data.get('test_mode', False)
    base_url = request.host_url
    
    # Start the sending process in a background thread
    Thread(target=campaign_controller.send_campaign_emails, 
           args=(user_id, campaign_id, test_mode, base_url)).start()
    
    return jsonify({
        'message': 'Test email sending in progress' if test_mode else 'Campaign sending in progress'
    }), 200
```

This route sends email campaigns:
1. Extract user ID, test mode flag, and base URL
2. Start the email sending process in a background thread to avoid blocking the request
3. Return an immediate response while emails are sent asynchronously

### Tracking Routes

```python
@app.route('/track/open/<tracking_pixel_id>', methods=['GET'])
def track_open(tracking_pixel_id):
    """Track email opens via tracking pixel"""
    return tracking_controller.track_email_open(tracking_pixel_id)

@app.route('/track/click/<tracking_id>/<url_tracking_id>', methods=['GET'])
def track_click(tracking_id, url_tracking_id):
    """Track email link clicks and also ensure opens are recorded"""
    return tracking_controller.track_email_click(tracking_id, url_tracking_id)
```

These routes handle email tracking:
1. Note that JWT authentication is not required for tracking endpoints
2. This allows tracking to work even when recipients are not logged in
3. Pass tracking IDs to the tracking controller
4. For opens, return a tracking pixel image
5. For clicks, redirect to the original URL after recording the click

## Main Entry Point

```python
# Main entry point
if __name__ == '__main__':
    # Set debug to False in production!
    app.run(debug=True, port=5000)
```

This standard Python idiom runs the Flask app when the file is executed directly, starting the development server on port 5000 with debug mode enabled.