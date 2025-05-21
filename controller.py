"""
Controller module that handles business logic for the Email Campaign Management API.
Validates inputs and calls the appropriate model functions.
"""
from flask import jsonify, current_app, redirect
from flask_jwt_extended import create_access_token
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import json
from threading import Thread

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

# ================== AUTH CONTROLLER ==================
class AuthController:
    @handle_transaction
    def register_user(self, data):
        # Validate required fields
        required_fields = ['email', 'password', 'full_name']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({'message': f'Missing required field: {field}'}), 422
        
        # Check if user exists
        existing_user = user_model.find_by_email(data['email'])
        if existing_user:
            return jsonify({'message': 'Email already registered'}), 400
        
        # Create new user
        password_hash = generate_password_hash(data['password'])
        user = user_model.create(data['email'], password_hash, data['full_name'])
        
        access_token = create_access_token(identity=str(user['user_id']))
        
        return jsonify({
            'message': 'User registered successfully',
            'access_token': access_token,
            'user': {
                'user_id': str(user['user_id']),
                'email': user['email'],
                'full_name': user['full_name']
            }
        }), 201
    
    @handle_transaction
    def login_user(self, data):
        # Validate required fields
        required_fields = ['email', 'password']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({'message': f'Missing required field: {field}'}), 422
        
        # Find user by email
        user = user_model.find_by_email(data['email'])
        
        # Verify credentials
        if not user or not check_password_hash(user['password_hash'], data['password']):
            return jsonify({'message': 'Invalid credentials'}), 401
        
        # Create JWT token
        access_token = create_access_token(identity=str(user['user_id']))
        
        return jsonify({
            'message': 'Login successful',
            'access_token': access_token,
            'user': {
                'user_id': str(user['user_id']),
                'email': user['email'],
                'full_name': user['full_name']
            }
        }), 200


# ================== CAMPAIGN CONTROLLER ==================
class CampaignController:
    @handle_transaction
    def get_all_campaigns(self, user_id):
        campaigns = campaign_model.get_all_by_user(user_id)
        
        result = []
        for campaign in campaigns:
            # Count recipients
            recipient_count = campaign_model.count_recipients(campaign['campaign_id'])
            
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
                
                stats['sent_count'] = sent_count
                stats['opened_count'] = opened_count
                stats['clicked_count'] = clicked_count
                stats['replied_count'] = replied_count
                
                # Calculate rates
                if sent_count > 0:
                    stats['open_rate'] = (opened_count / sent_count) * 100
                    stats['click_rate'] = (clicked_count / sent_count) * 100
                    stats['reply_rate'] = (replied_count / sent_count) * 100
            
            # Prepare campaign data
            campaign_data = dict(campaign)
            campaign_data['recipient_count'] = recipient_count
            campaign_data['stats'] = stats
            
            # Convert UUIDs to strings for JSON serialization
            campaign_data['campaign_id'] = str(campaign_data['campaign_id'])
            campaign_data['user_id'] = str(campaign_data['user_id'])
            
            # Format dates
            for key in ['created_at', 'scheduled_at', 'sent_at']:
                if key in campaign_data and campaign_data[key]:
                    campaign_data[key] = campaign_data[key].isoformat()
            
            result.append(campaign_data)
        
        return jsonify(result), 200
    
    @handle_transaction
    def create_new_campaign(self, user_id, data):
        # Validate required fields
        required_fields = ['campaign_name', 'subject_line', 'from_name', 'from_email', 'reply_to_email']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({'message': f'Missing required field: {field}'}), 422
        
        # Create campaign
        campaign_id = campaign_model.create(
            user_id, 
            data['campaign_name'], 
            data['subject_line'], 
            data['from_name'],
            data['from_email'],
            data['reply_to_email']
        )
        
        # Create template if provided
        if 'template' in data:
            template_name = data['template'].get('name', 'Default Template')
            html_content = data['template']['html_content']
            text_content = data['template'].get('text_content', '')
            
            template_model.create(user_id, campaign_id, template_name, html_content, text_content)
        
        # Add recipients if provided
        if 'recipients' in data:
            for recipient_id in data['recipients']:
                # Verify recipient belongs to user
                recipient = recipient_model.find_by_id(recipient_id, user_id)
                
                if recipient:
                    campaign_model.add_recipient(campaign_id, recipient_id)
        
        return jsonify({
            'message': 'Campaign created successfully',
            'campaign_id': str(campaign_id)
        }), 201
    
    @handle_transaction
    def get_campaign_by_id(self, user_id, campaign_id):
        # Get campaign details
        campaign = campaign_model.find_by_id(campaign_id, user_id)
        
        if not campaign:
            return jsonify({'message': 'Campaign not found'}), 404
        
        # Get template
        template = template_model.find_by_campaign_id(campaign_id)
        
        # Get recipients
        recipients = campaign_model.get_recipients(campaign_id)
        
        recipient_list = []
        for recipient in recipients:
            recipient_data = dict(recipient)
            recipient_data['recipient_id'] = str(recipient_data['recipient_id'])
            recipient_data['user_id'] = str(recipient_data['user_id'])
            recipient_list.append(recipient_data)
        
        # Get tracking stats if campaign sent
        tracking_stats = None
        if campaign['status'] == 'completed':
            overall_stats = campaign_model.get_tracking_stats(campaign_id)
            
            # Get individual recipient tracking
            recipient_tracking = tracking_model.get_by_campaign(campaign_id)
            
            # Calculate rates
            sent_count = overall_stats['sent_count']
            opened_count = overall_stats['opened_count']
            clicked_count = overall_stats['clicked_count']
            replied_count = overall_stats['replied_count']
            
            open_rate = (opened_count / sent_count * 100) if sent_count > 0 else 0
            click_rate = (clicked_count / sent_count * 100) if sent_count > 0 else 0
            reply_rate = (replied_count / sent_count * 100) if sent_count > 0 else 0
            
            # Format recipient tracking data
            recipient_tracking_list = []
            for tracking in recipient_tracking:
                tracking_data = dict(tracking)
                for key in ['tracking_id', 'campaign_id', 'recipient_id']:
                    if key in tracking_data and tracking_data[key]:
                        tracking_data[key] = str(tracking_data[key])
                
                # Format dates to ISO strings
                for key in ['sent_at', 'opened_at', 'clicked_at', 'replied_at', 'created_at', 'updated_at']:
                    if key in tracking_data and tracking_data[key]:
                        tracking_data[key] = tracking_data[key].isoformat()
                
                recipient_tracking_list.append(tracking_data)
            
            tracking_stats = {
                'overall': {
                    'sent_count': sent_count,
                    'opened_count': opened_count,
                    'clicked_count': clicked_count,
                    'replied_count': replied_count,
                    'open_rate': open_rate,
                    'click_rate': click_rate,
                    'reply_rate': reply_rate
                },
                'recipients': recipient_tracking_list
            }
        
        # Prepare template data
        template_data = None
        if template:
            template_data = dict(template)
            template_data['template_id'] = str(template_data['template_id'])
            template_data['user_id'] = str(template_data['user_id'])
            template_data['campaign_id'] = str(template_data['campaign_id'])
            
            # Format dates
            for key in ['created_at', 'updated_at']:
                if key in template_data and template_data[key]:
                    template_data[key] = template_data[key].isoformat()
        
        # Prepare campaign data
        campaign_data = dict(campaign)
        campaign_data['campaign_id'] = str(campaign_data['campaign_id'])
        campaign_data['user_id'] = str(campaign_data['user_id'])
        
        # Format dates
        for key in ['created_at', 'scheduled_at', 'sent_at']:
            if key in campaign_data and campaign_data[key]:
                campaign_data[key] = campaign_data[key].isoformat()
        
        result = {
            **campaign_data,
            'template': template_data,
            'recipients': recipient_list,
            'tracking_stats': tracking_stats
        }
        
        return jsonify(result), 200
    
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
    
    @handle_transaction
    def get_dashboard_overview(self, user_id):
        """Get dashboard overview data"""
        # Get counts
        campaign_count = campaign_model.count_by_user(user_id)
        recipient_count = recipient_model.count_by_user(user_id)
        template_count = template_model.count_by_user(user_id)
        
        # Get completed campaigns
        completed_campaigns = campaign_model.get_completed_by_user(user_id)
        
        # Calculate stats
        total_sent = 0
        total_opened = 0
        total_clicked = 0
        total_replied = 0
        
        campaign_stats = []
        
        for campaign in completed_campaigns:
            tracking = campaign_model.get_tracking_stats(campaign['campaign_id'])
            
            sent_count = tracking['sent_count']
            opened_count = tracking['opened_count']
            clicked_count = tracking['clicked_count']
            replied_count = tracking['replied_count']
            
            total_sent += sent_count
            total_opened += opened_count
            total_clicked += clicked_count
            total_replied += replied_count
            
            open_rate = (opened_count / sent_count * 100) if sent_count > 0 else 0
            click_rate = (clicked_count / sent_count * 100) if sent_count > 0 else 0
            reply_rate = (replied_count / sent_count * 100) if sent_count > 0 else 0
            
            campaign_data = dict(campaign)
            campaign_data['campaign_id'] = str(campaign_data['campaign_id'])
            campaign_data['user_id'] = str(campaign_data['user_id'])
            
            # Format dates
            for key in ['created_at', 'scheduled_at', 'sent_at']:
                if key in campaign_data and campaign_data[key]:
                    campaign_data[key] = campaign_data[key].isoformat()
            
            campaign_stats.append({
                **campaign_data,
                'sent_count': sent_count,
                'opened_count': opened_count,
                'clicked_count': clicked_count,
                'replied_count': replied_count,
                'open_rate': open_rate,
                'click_rate': click_rate,
                'reply_rate': reply_rate
            })
        
        overall_open_rate = (total_opened / total_sent * 100) if total_sent > 0 else 0
        overall_click_rate = (total_clicked / total_sent * 100) if total_sent > 0 else 0
        overall_reply_rate = (total_replied / total_sent * 100) if total_sent > 0 else 0
        
        # Get recent campaigns
        recent_campaigns = campaign_model.get_recent_by_user(user_id, limit=5)
        recent_campaign_data = []
        
        for campaign in recent_campaigns:
            campaign_data = dict(campaign)
            campaign_data['campaign_id'] = str(campaign_data['campaign_id'])
            campaign_data['user_id'] = str(campaign_data['user_id'])
            
            # Format dates
            for key in ['created_at', 'scheduled_at', 'sent_at']:
                if key in campaign_data and campaign_data[key]:
                    campaign_data[key] = campaign_data[key].isoformat()
            
            recent_campaign_data.append(campaign_data)
        
        # Get recent recipients
        recent_recipients = recipient_model.get_recent_by_user(user_id, limit=5)
        recent_recipient_data = []
        
        for recipient in recent_recipients:
            recipient_data = dict(recipient)
            recipient_data['recipient_id'] = str(recipient_data['recipient_id'])
            recipient_data['user_id'] = str(recipient_data['user_id'])
            
            # Format dates
            for key in ['created_at', 'updated_at']:
                if key in recipient_data and recipient_data[key]:
                    recipient_data[key] = recipient_data[key].isoformat()
            
            recent_recipient_data.append(recipient_data)
        
        result = {
            'counts': {
                'campaigns': campaign_count,
                'recipients': recipient_count,
                'templates': template_count,
                'emails_sent': total_sent
            },
            'overall_stats': {
                'total_sent': total_sent,
                'total_opened': total_opened,
                'total_clicked': total_clicked,
                'total_replied': total_replied,
                'open_rate': overall_open_rate,
                'click_rate': overall_click_rate,
                'reply_rate': overall_reply_rate
            },
            'campaign_stats': campaign_stats,
            'recent_campaigns': recent_campaign_data,
            'recent_recipients': recent_recipient_data
        }
        return jsonify(result), 200


# ================== RECIPIENT CONTROLLER ==================
class RecipientController:
    @handle_transaction
    def get_all_recipients(self, user_id):
        recipients = recipient_model.get_all_by_user(user_id)
        
        result = []
        for recipient in recipients:
            recipient_data = dict(recipient)
            recipient_data['recipient_id'] = str(recipient_data['recipient_id'])
            recipient_data['user_id'] = str(recipient_data['user_id'])
            
            # Format dates
            for key in ['created_at', 'updated_at']:
                if key in recipient_data and recipient_data[key]:
                    recipient_data[key] = recipient_data[key].isoformat()
            
            result.append(recipient_data)
        
        return jsonify(result), 200
    
    @handle_transaction
    def create_new_recipient(self, user_id, data):
        # Validate required fields
        if 'email' not in data or not data['email']:
            return jsonify({'message': 'Email is required'}), 422
        
        # Check if recipient already exists
        existing = recipient_model.find_by_email(user_id, data['email'])
        
        if existing:
            return jsonify({'message': 'Recipient with this email already exists'}), 400
        
        # Create new recipient
        custom_fields = json.dumps(data.get('custom_fields', {})) if data.get('custom_fields') else None
        
        recipient_id = recipient_model.create(
            user_id,
            data['email'],
            data.get('first_name'),
            data.get('last_name'),
            data.get('company'),
            data.get('position'),
            custom_fields
        )
        
        return jsonify({
            'message': 'Recipient created successfully',
            'recipient_id': str(recipient_id)
        }), 201
    
    @handle_transaction
    def create_bulk_recipients(self, user_id, data):
        # Validate data
        if not data or 'recipients' not in data:
            return jsonify({'message': 'No recipients provided'}), 400
        
        created_count = 0
        skipped_count = 0
        
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
        
        return jsonify({
            'message': f'Created {created_count} recipients, skipped {skipped_count} duplicates',
            'created_count': created_count,
            'skipped_count': skipped_count
        }), 201
    
    @handle_transaction
    def get_recipient_by_id(self, user_id, recipient_id):
        # Get recipient by ID and verify ownership
        recipient = recipient_model.find_by_id(recipient_id, user_id)
        
        if not recipient:
            return jsonify({'message': 'Recipient not found or access denied'}), 404
        
        # Convert to dictionary and handle UUID serialization
        result = dict(recipient)
        result['recipient_id'] = str(result['recipient_id'])
        result['user_id'] = str(result['user_id'])
        
        # Format dates
        for key in ['created_at', 'updated_at']:
            if key in result and result[key]:
                result[key] = result[key].isoformat()
        
        return jsonify(result), 200
    
    @handle_transaction
    def update_existing_recipient(self, user_id, recipient_id, data):
        # Validate required fields
        if 'email' not in data or not data['email']:
            return jsonify({'message': 'Email is required'}), 422
        
        # Verify recipient exists and belongs to user
        recipient = recipient_model.find_by_id(recipient_id, user_id)
        
        if not recipient:
            return jsonify({'message': 'Recipient not found or access denied'}), 404
        
        # Check if updating to an email that already exists (for another recipient)
        if data['email'] != recipient['email']:
            existing = recipient_model.find_by_email_excluding(user_id, data['email'], recipient_id)
            
            if existing:
                return jsonify({'message': 'Another recipient with this email already exists'}), 400
        
        # Handle custom fields as JSON
        custom_fields = json.dumps(data.get('custom_fields', {})) if data.get('custom_fields') else None
        
        # Update recipient
        updated_id = recipient_model.update(
            recipient_id,
            data['email'],
            data.get('first_name'),
            data.get('last_name'),
            data.get('company'),
            data.get('position'),
            custom_fields
        )
        
        return jsonify({
            'message': 'Recipient updated successfully',
            'recipient_id': str(updated_id)
        }), 200
    
    @handle_transaction
    def delete_recipient_by_id(self, user_id, recipient_id):
        # Verify recipient exists and belongs to user
        recipient = recipient_model.find_by_id(recipient_id, user_id)
        
        if not recipient:
            return jsonify({'message': 'Recipient not found or access denied'}), 404
        
        # Soft delete the recipient by setting is_active to FALSE
        recipient_model.soft_delete(recipient_id)
        
        # Also remove recipient from any campaign_recipients
        recipient_model.remove_from_campaigns(recipient_id)
        
        return jsonify({
            'message': 'Recipient deleted successfully',
            'recipient_id': recipient_id
        }), 200
    
    @handle_transaction
    def delete_bulk_recipients(self, user_id, data):
        # Validate data
        if not data or 'recipient_ids' not in data or not data['recipient_ids']:
            return jsonify({'message': 'No recipient IDs provided'}), 400
        
        # Convert recipient_ids to a list if it's a single value
        recipient_ids = data['recipient_ids']
        if not isinstance(recipient_ids, list):
            recipient_ids = [recipient_ids]
        
        # Get recipients that belong to the user
        valid_recipient_ids = recipient_model.validate_ownership(user_id, recipient_ids)
        
        if not valid_recipient_ids:
            return jsonify({'message': 'No valid recipients found'}), 404
        
        # Soft delete the recipients
        recipient_model.soft_delete_bulk(valid_recipient_ids)
        
        # Remove recipients from any campaign_recipients
        recipient_model.remove_bulk_from_campaigns(valid_recipient_ids)
        
        return jsonify({
            'message': f'Successfully deleted {len(valid_recipient_ids)} recipients',
            'deleted_count': len(valid_recipient_ids),
            'recipient_ids': valid_recipient_ids
        }), 200


# ================== TEMPLATE CONTROLLER ==================
class TemplateController:
    @handle_transaction
    def get_all_templates(self, user_id):
        templates = template_model.get_all_by_user(user_id)
        
        result = []
        for template in templates:
            template_data = dict(template)
            template_data['template_id'] = str(template_data['template_id'])
            template_data['user_id'] = str(template_data['user_id'])
            if template_data['campaign_id']:
                template_data['campaign_id'] = str(template_data['campaign_id'])
            
            # Format dates
            for key in ['created_at', 'updated_at']:
                if key in template_data and template_data[key]:
                    template_data[key] = template_data[key].isoformat()
            
            result.append(template_data)
        
        return jsonify(result), 200


# ================== TRACKING CONTROLLER ==================
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
        
        except Exception as e:
            current_app.logger.error(f"❌ Error tracking open: {str(e)}")
            return tracking_model.get_fallback_pixel(), 200, {'Content-Type': 'image/gif'}
    
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
            
        except Exception as e:
            current_app.logger.error(f"❌ Error tracking click: {str(e)}")
            # Provide a fallback in case of error
            return redirect("https://www.google.com", code=302)
    
    def track_email_beacon(self, tracking_pixel_id):
        """JavaScript-based tracking endpoint as backup for image tracking"""
        try:
            current_app.logger.info(f"🔍 Beacon tracking accessed: {tracking_pixel_id}")
            tracking_model.record_beacon(tracking_pixel_id)
            
            return jsonify({'status': 'ok'}), 200, {
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Access-Control-Allow-Origin': '*'
            }
        
        except Exception as e:
            current_app.logger.error(f"❌ Error tracking beacon: {str(e)}")
            return jsonify({'status': 'error'}), 200  # Return 200 even on error to avoid JS errors
    
    def mark_email_as_replied(self, user_id, campaign_id, data):
        """Manually mark an email as replied"""
        try:
            # Validate input
            if not data or 'recipient_id' not in data:
                return jsonify({'message': 'Recipient ID is required'}), 400
            
            recipient_id = data['recipient_id']
            current_app.logger.info(f"Attempting to mark recipient {recipient_id} as replied for campaign {campaign_id}")
            
            # Verify campaign belongs to user
            campaign = campaign_model.find_by_id(campaign_id, user_id)
            
            if not campaign:
                return jsonify({'message': 'Campaign not found or access denied'}), 404
            
            # Update tracking record
            result = tracking_model.mark_as_replied(campaign_id, recipient_id)
            
            if not result:
                current_app.logger.warning(f"No tracking record found for recipient {recipient_id} in campaign {campaign_id}")
                return jsonify({'message': 'No tracking record found for this recipient'}), 404
            
            current_app.logger.info(f"Successfully marked recipient {recipient_id} as replied for campaign {campaign_id}")
            
            return jsonify({
                'message': 'Email marked as replied successfully',
                'tracking_id': str(result['tracking_id']),
                'replied_at': result['replied_at'].isoformat()
            }), 200
            
        except Exception as e:
            current_app.logger.error(f"Error marking email as replied: {str(e)}")
            return jsonify({'message': f'Error: {str(e)}'}), 500


# ================== DEBUG CONTROLLER ==================
class DebugController:
    def test_auth(self, user_id):
        """Test endpoint that requires authentication"""
        return jsonify({
            'status': 'success',
            'message': 'Authentication successful',
            'user_id': user_id,
            'timestamp': datetime.now().isoformat()
        }), 200
    
    def check_health(self):
        """Health check endpoint that doesn't require authentication"""
        return jsonify({
            'status': 'success',
            'message': 'API is online',
            'timestamp': datetime.now().isoformat()
        }), 200
    
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
            
            return jsonify({
                'campaign_id': campaign_id,
                'tracking_count': len(tracking_data),
                'tracking_data': tracking_data,
                'url_tracking': url_data,
                'timestamp': datetime.now().isoformat()
            }), 200
            
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    def trigger_reply_checking(self):
        """Function to be called in a background thread"""
        check_for_replies()
    
    def get_reply_check_response(self, user_id):
        """Return response for manual reply check trigger"""
        return jsonify({
            'message': 'Reply check started in background',
            'user_id': user_id,
            'timestamp': datetime.now().isoformat()
        }), 200
    
    def manually_track_open(self, campaign_id, recipient_id):
        """Debug endpoint to manually trigger an open tracking event"""
        try:
            result = tracking_model.manual_record_open(campaign_id, recipient_id)
            
            if not result:
                return jsonify({
                    'message': 'No tracking entry found for this campaign and recipient'
                }), 404
            
            return jsonify({
                'message': 'Successfully recorded open event',
                'tracking_id': str(result['tracking_id']),
                'opened_at': result['opened_at'].isoformat(),
                'open_count': result['open_count']
            }), 200
        except Exception as e:
            return jsonify({
                'message': f'Error: {str(e)}'
            }), 500
    
    def generate_test_click(self, tracking_id):
        """Generate a test click for debugging"""
        try:
            result = tracking_model.create_test_click(tracking_id)
            if not result:
                return jsonify({'message': 'Error creating test click'}), 500
                
            # Redirect to the click tracking URL
            return redirect(f"/track/click/{tracking_id}/{result['url_tracking_id']}", code=302)
            
        except Exception as e:
            return jsonify({'error': str(e)}), 500


# Initialize controller instances
auth_controller = AuthController()
campaign_controller = CampaignController()
recipient_controller = RecipientController()
template_controller = TemplateController()
tracking_controller = TrackingController()
debug_controller = DebugController()