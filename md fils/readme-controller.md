# controller.py - Detailed Documentation

## Overview

`controller.py` contains the business logic for the Email Campaign Management API. It acts as an intermediary between the routes in `app.py` and the database operations in `models.py`. Controllers validate input data, process business rules, call model functions, and format the responses.

## Imports

```python
from flask import jsonify, current_app, redirect
from flask_jwt_extended import create_access_token
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import json
from threading import Thread
```

- **jsonify**: Converts Python objects to JSON responses
- **current_app**: Access to the Flask application context
- **redirect**: HTTP redirect response for tracking links
- **create_access_token**: Creates JWT tokens for authentication
- **generate_password_hash/check_password_hash**: Password hashing and verification
- **datetime**: Date and time operations
- **json**: JSON serialization and deserialization
- **Thread**: For background processing

```python
# Import models
from models import (
    user_model,
    campaign_model,
    recipient_model,
    template_model,
    tracking_model
)

# Import helpers
from helper import (
    to_dict, 
    to_list,
    handle_transaction,
    send_email_async,
    check_for_replies,
    get_direct_db_connection
)
```

These import the model instances and helper functions that will be used by the controllers.

## AuthController

```python
class AuthController:
    @handle_transaction
    def register_user(self, data):
        # Validate required fields
        required_fields = ['email', 'password', 'full_name']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({'message': f'Missing required field: {field}'}), 422
```

The `register_user` method:
1. Uses `@handle_transaction` decorator to manage database transactions
2. Validates required fields (email, password, full_name)
3. Returns a 422 error if any required fields are missing

```python
        # Check if user exists
        existing_user = user_model.find_by_email(data['email'])
        if existing_user:
            return jsonify({'message': 'Email already registered'}), 400
```

This code:
1. Checks if a user with the provided email already exists
2. Returns a 400 error if the email is already registered

```python
        # Create new user
        password_hash = generate_password_hash(data['password'])
        user = user_model.create(data['email'], password_hash, data['full_name'])
        
        access_token = create_access_token(identity=str(user['user_id']))
```

Here, the controller:
1. Hashes the password for secure storage
2. Creates a new user in the database
3. Generates a JWT token with the user ID as the identity

```python
        return jsonify({
            'message': 'User registered successfully',
            'access_token': access_token,
            'user': {
                'user_id': str(user['user_id']),
                'email': user['email'],
                'full_name': user['full_name']
            }
        }), 201
```

Finally, it returns:
1. A success message
2. The JWT access token
3. Basic user information
4. HTTP status 201 (Created)

The `login_user` method has similar structure but validates credentials against existing users.

## CampaignController

```python
class CampaignController:
    @handle_transaction
    def get_all_campaigns(self, user_id):
        campaigns = campaign_model.get_all_by_user(user_id)
        
        result = []
        for campaign in campaigns:
            # Count recipients
            recipient_count = campaign_model.count_recipients(campaign['campaign_id'])
```

The `get_all_campaigns` method:
1. Gets all campaigns for the user
2. Counts recipients for each campaign

```python
            # Get tracking stats
            stats = {
                'sent_count': 0,
                'opened_count': 0,
                'clicked_count': 0,
                'replied_count': 0,
                'open_rate': 0,
                'click_rate': 0,
                'reply_rate': 0
            }
            
            # Only get tracking stats for completed campaigns
            if campaign['status'] == 'completed':
                tracking = campaign_model.get_tracking_stats(campaign['campaign_id'])
                
                sent_count = tracking['sent_count']
                opened_count = tracking['opened_count']
                clicked_count = tracking['clicked_count']
                replied_count = tracking['replied_count']
```

This section:
1. Initializes tracking statistics
2. Gets actual tracking data for completed campaigns
3. Extracts counts for sent, opened, clicked, and replied emails

```python
                # Calculate rates
                if sent_count > 0:
                    stats['open_rate'] = (opened_count / sent_count) * 100
                    stats['click_rate'] = (clicked_count / sent_count) * 100
                    stats['reply_rate'] = (replied_count / sent_count) * 100
```

Calculates performance rates if any emails were sent.

```python
            # Prepare campaign data
            campaign_data = dict(campaign)
            campaign_data['recipient_count'] = recipient_count
            campaign_data['stats'] = stats
            
            # Convert UUIDs to strings for JSON serialization
            campaign_data['campaign_id'] = str(campaign_data['campaign_id'])
            campaign_data['user_id'] = str(campaign_data['user_id'])
```

Formats the campaign data by:
1. Adding recipient count and stats
2. Converting UUID fields to strings for JSON serialization

```python
            # Format dates
            for key in ['created_at', 'scheduled_at', 'sent_at']:
                if key in campaign_data and campaign_data[key]:
                    campaign_data[key] = campaign_data[key].isoformat()
            
            result.append(campaign_data)
        
        return jsonify(result), 200
```

Formats dates as ISO strings and returns the JSON response with HTTP status 200.

### Send Campaign Emails Method

```python
    def send_campaign_emails(self, user_id, campaign_id, test_mode, base_url):
        """
        Send campaign emails in a background process.
        This method is called in a new thread.
        """
        if not test_mode:
            # Verify campaign exists and belongs to user
            campaign = campaign_model.find_by_id(campaign_id, user_id)
            
            if not campaign:
                current_app.logger.error(f"Campaign {campaign_id} not found for user {user_id}")
                return
            
            # Update campaign status to 'sending'
            campaign_model.update_status(campaign_id, 'sending')
        
        # Call the email sending function
        send_email_async(campaign_id, test_mode, base_url)
```

This method:
1. Is designed to run in a background thread
2. Verifies campaign existence and ownership (unless in test mode)
3. Updates campaign status to 'sending'
4. Calls the asynchronous email sending function

## RecipientController

```python
class RecipientController:
    @handle_transaction
    def create_bulk_recipients(self, user_id, data):
        # Validate data
        if not data or 'recipients' not in data:
            return jsonify({'message': 'No recipients provided'}), 400
        
        created_count = 0
        skipped_count = 0
```

The `create_bulk_recipients` method:
1. Validates that recipient data was provided
2. Initializes counters for created and skipped recipients

```python
        for recipient_data in data['recipients']:
            # Skip if no email
            if 'email' not in recipient_data or not recipient_data['email']:
                skipped_count += 1
                continue
            
            # Check if recipient already exists
            existing = recipient_model.find_by_email(user_id, recipient_data['email'])
            
            if existing:
                skipped_count += 1
                continue
```

For each recipient:
1. Skips if email is missing
2. Checks if the recipient already exists
3. Skips duplicates

```python
            # Create new recipient
            custom_fields = json.dumps(recipient_data.get('custom_fields', {})) if recipient_data.get('custom_fields') else None
            
            recipient_model.create(
                user_id,
                recipient_data['email'],
                recipient_data.get('first_name'),
                recipient_data.get('last_name'),
                recipient_data.get('company'),
                recipient_data.get('position'),
                custom_fields
            )
            
            created_count += 1
```

Creates new recipients in the database and increments the counter.

```python
        return jsonify({
            'message': f'Created {created_count} recipients, skipped {skipped_count} duplicates',
            'created_count': created_count,
            'skipped_count': skipped_count
        }), 201
```

Returns a summary of the bulk operation with counts of created and skipped recipients.

## TrackingController

```python
class TrackingController:
    def track_email_open(self, tracking_pixel_id):
        """Track email opens via tracking pixel"""
        try:
            current_app.logger.info(f"🔍 Tracking pixel accessed: {tracking_pixel_id}")
            result = tracking_model.record_open(tracking_pixel_id)
            
            # Return a 1x1 transparent pixel
            pixel = result['pixel']
            
            return pixel, 200, {
                'Content-Type': 'image/gif', 
                'Cache-Control': 'no-cache, no-store, must-revalidate, private',
                'Pragma': 'no-cache',
                'Expires': '0'
            }
```

The `track_email_open` method:
1. Logs the tracking event
2. Records the email open in the database
3. Returns a 1x1 transparent GIF image with cache headers to prevent browser caching
4. This special GIF response is what makes the tracking pixel work - the email client loads the image, triggering the tracking

```python
    def track_email_click(self, tracking_id, url_tracking_id):
        """Track email link clicks and also ensure opens are recorded"""
        try:
            current_app.logger.info(f"🔍 Click tracking: tracking_id={tracking_id}, url_tracking_id={url_tracking_id}")
            result = tracking_model.record_click(tracking_id, url_tracking_id)
            
            if not result:
                # Fallback to a safe URL if the tracking entry isn't found
                return redirect("https://www.google.com", code=302)
            
            # Redirect to the original URL
            return redirect(result['original_url'], code=302)
```

The `track_email_click` method:
1. Logs the click tracking event
2. Records the click in the database
3. Redirects to the original URL (or a fallback URL if tracking fails)
4. The 302 redirect preserves the original link functionality while tracking the click

## DebugController

```python
class DebugController:
    def get_tracking_debug_data(self, user_id, campaign_id):
        """Debug endpoint to directly query tracking data"""
        try:
            # Verify campaign belongs to user
            campaign = campaign_model.find_by_id(campaign_id, user_id)
            
            if not campaign:
                return jsonify({'message': 'Campaign not found or access denied'}), 404
            
            # Get raw tracking data from database
            tracking_data = tracking_model.get_debug_data(campaign_id)
            
            # Get URL tracking data too
            url_data = tracking_model.get_debug_url_data(campaign_id)
```

This debug method:
1. Verifies campaign ownership
2. Gets both email tracking and URL tracking data
3. Used for debugging tracking issues and monitoring campaign performance

```python
            return jsonify({
                'campaign_id': campaign_id,
                'tracking_count': len(tracking_data),
                'tracking_data': tracking_data,
                'url_tracking': url_data,
                'timestamp': datetime.now().isoformat()
            }), 200
```

Returns detailed tracking data for debugging purposes.

## Controller Instances

```python
# Initialize controller instances
auth_controller = AuthController()
campaign_controller = CampaignController()
recipient_controller = RecipientController()
template_controller = TemplateController()
tracking_controller = TrackingController()
debug_controller = DebugController()
```

Creates instances of each controller class to be imported and used by the routes in `app.py`.