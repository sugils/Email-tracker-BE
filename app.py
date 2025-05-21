"""
Main application file for the Email Campaign Management API.
Defines all API routes and connects to the appropriate controllers.
"""
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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
)

# Initialize Flask app
app = Flask(__name__)

# Configure CORS to allow cross-origin requests
CORS(app, 
     resources={r"/*": {"origins": "*"}},
     supports_credentials=True,
     allow_headers=["Content-Type", "Authorization", "X-Requested-With", "Accept", "Origin"],
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
     expose_headers=["Content-Type", "Authorization"])

# Generate a secret key for JWT tokens
generated_key = secrets.token_hex(32)

# JWT Configuration
app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY', generated_key)
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=1)

app.logger.info(f"Using JWT secret key: {app.config['JWT_SECRET_KEY'][:8]}...") # Show first 8 chars for debugging

# Initialize the JWT manager
jwt = JWTManager(app)

# Clean up the database connection at the end of each request
@app.teardown_appcontext
def teardown_db(exception):
    close_db_connection(exception)

# Initialize scheduler for checking replies - runs every minute
scheduler = BackgroundScheduler()
def scheduled_safe_check():
    with app.app_context():
        safe_check_for_replies()
scheduler.add_job(func=scheduled_safe_check, trigger="interval", minutes=1)
scheduler.start()

# Shut down the scheduler when exiting the app
atexit.register(lambda: scheduler.shutdown())

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

# Initialize database on app startup
with app.app_context():
    from models import init_db
    init_db()

# ==================== ROUTES ====================

# Authentication Routes
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

# Campaign Routes
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

@app.route('/api/campaigns/<campaign_id>', methods=['GET'])
@jwt_required()
def get_campaign(campaign_id):
    """Get a single campaign by ID"""
    user_id = get_jwt_identity()
    return campaign_controller.get_campaign_by_id(user_id, campaign_id)

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

# Recipient Routes
@app.route('/api/recipients', methods=['GET'])
@jwt_required()
def get_recipients():
    """Get all recipients for current user"""
    user_id = get_jwt_identity()
    return recipient_controller.get_all_recipients(user_id)

@app.route('/api/recipients', methods=['POST'])
@jwt_required()
def create_recipient():
    """Create a new recipient"""
    user_id = get_jwt_identity()
    data = request.get_json()
    return recipient_controller.create_new_recipient(user_id, data)

@app.route('/api/recipients/bulk', methods=['POST'])
@jwt_required()
def create_recipients_bulk():
    """Create multiple recipients at once"""
    user_id = get_jwt_identity()
    data = request.get_json()
    return recipient_controller.create_bulk_recipients(user_id, data)

@app.route('/api/recipients/<recipient_id>', methods=['GET'])
@jwt_required()
def get_recipient(recipient_id):
    """Get a single recipient by ID"""
    user_id = get_jwt_identity()
    return recipient_controller.get_recipient_by_id(user_id, recipient_id)

@app.route('/api/recipients/<recipient_id>', methods=['PUT'])
@jwt_required()
def update_recipient(recipient_id):
    """Update an existing recipient"""
    user_id = get_jwt_identity()
    data = request.get_json()
    return recipient_controller.update_existing_recipient(user_id, recipient_id, data)

@app.route('/api/recipients/<recipient_id>', methods=['DELETE'])
@jwt_required()
def delete_recipient(recipient_id):
    """Delete a single recipient by ID"""
    user_id = get_jwt_identity()
    return recipient_controller.delete_recipient_by_id(user_id, recipient_id)

@app.route('/api/recipients/bulk-delete', methods=['POST'])
@jwt_required()
def bulk_delete_recipients():
    """Delete multiple recipients at once"""
    user_id = get_jwt_identity()
    data = request.get_json()
    return recipient_controller.delete_bulk_recipients(user_id, data)

# Template Routes
@app.route('/api/templates', methods=['GET'])
@jwt_required()
def get_templates():
    """Get all templates for current user"""
    user_id = get_jwt_identity()
    return template_controller.get_all_templates(user_id)

# Tracking Routes
@app.route('/track/open/<tracking_pixel_id>', methods=['GET'])
def track_open(tracking_pixel_id):
    """Track email opens via tracking pixel"""
    return tracking_controller.track_email_open(tracking_pixel_id)

@app.route('/track/click/<tracking_id>/<url_tracking_id>', methods=['GET'])
def track_click(tracking_id, url_tracking_id):
    """Track email link clicks and also ensure opens are recorded"""
    return tracking_controller.track_email_click(tracking_id, url_tracking_id)

@app.route('/track/beacon/<tracking_pixel_id>', methods=['GET'])
def track_beacon(tracking_pixel_id):
    """JavaScript-based tracking endpoint as backup for image tracking"""
    return tracking_controller.track_email_beacon(tracking_pixel_id)

@app.route('/api/campaigns/<campaign_id>/mark-replied', methods=['POST'])
@jwt_required()
def mark_email_replied(campaign_id):
    """Manually mark an email as replied"""
    user_id = get_jwt_identity()
    data = request.get_json()
    return tracking_controller.mark_email_as_replied(user_id, campaign_id, data)

# Dashboard Routes
@app.route('/api/dashboard', methods=['GET'])
@jwt_required()
def get_dashboard_data():
    """Get dashboard overview data"""
    user_id = get_jwt_identity()
    return campaign_controller.get_dashboard_overview(user_id)

# Utility and debugging routes
@app.route('/api/auth-test', methods=['GET'])
@jwt_required()
def auth_test():
    """Test endpoint that requires authentication"""
    current_user_id = get_jwt_identity()
    return debug_controller.test_auth(current_user_id)

@app.route('/api/health-check', methods=['GET'])
def health_check():
    """Health check endpoint that doesn't require authentication"""
    return debug_controller.check_health()

@app.route('/api/debug/tracking/<campaign_id>', methods=['GET'])
@jwt_required()
def debug_tracking(campaign_id):
    """Debug endpoint to directly query tracking data"""
    user_id = get_jwt_identity()
    return debug_controller.get_tracking_debug_data(user_id, campaign_id)

@app.route('/api/debug/check-replies', methods=['GET'])
@jwt_required()
def trigger_reply_check():
    """Manually trigger the email reply check"""
    user_id = get_jwt_identity()
    Thread(target=debug_controller.trigger_reply_checking).start()
    return debug_controller.get_reply_check_response(user_id)

@app.route('/api/debug/track-open/<campaign_id>/<recipient_id>', methods=['GET'])
def debug_track_open(campaign_id, recipient_id):
    """Debug endpoint to manually trigger an open tracking event"""
    return debug_controller.manually_track_open(campaign_id, recipient_id)

@app.route('/api/debug/test-click/<tracking_id>', methods=['GET'])
def test_click(tracking_id):
    """Generate a test click for debugging"""
    return debug_controller.generate_test_click(tracking_id)

# Main entry point
if __name__ == '__main__':
    # Set debug to False in production!
    app.run(debug=True, port=5000)