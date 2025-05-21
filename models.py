"""
Models module that handles database operations for the Email Campaign Management API.
Contains functions for CRUD operations on all database tables.
"""
from flask import current_app, g
import json
import uuid
import base64
from datetime import datetime
import psycopg2
import psycopg2.extras
from helper import get_db_connection, get_direct_db_connection

# ==================== DATABASE INITIALIZATION ====================
def init_db():
    """Create database tables if they don't exist"""
    conn, cur = get_db_connection()
    
    # Create users table
    cur.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        email VARCHAR(255) NOT NULL UNIQUE,
        password_hash VARCHAR(255) NOT NULL,
        full_name VARCHAR(255) NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        is_active BOOLEAN DEFAULT TRUE
    )
    ''')
    
    # Create email_campaigns table
    cur.execute('''
    CREATE TABLE IF NOT EXISTS email_campaigns (
        campaign_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID NOT NULL REFERENCES users(user_id),
        campaign_name VARCHAR(255) NOT NULL,
        subject_line VARCHAR(255) NOT NULL,
        from_name VARCHAR(255) NOT NULL,
        from_email VARCHAR(255) NOT NULL,
        reply_to_email VARCHAR(255) NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        scheduled_at TIMESTAMP WITH TIME ZONE,
        sent_at TIMESTAMP WITH TIME ZONE,
        status VARCHAR(50) DEFAULT 'draft',
        is_active BOOLEAN DEFAULT TRUE
    )
    ''')
    
    # Create email_templates table
    cur.execute('''
    CREATE TABLE IF NOT EXISTS email_templates (
        template_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID NOT NULL REFERENCES users(user_id),
        campaign_id UUID REFERENCES email_campaigns(campaign_id),
        template_name VARCHAR(255) NOT NULL,
        html_content TEXT NOT NULL,
        text_content TEXT,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        is_active BOOLEAN DEFAULT TRUE
    )
    ''')
    
    # Create recipients table
    cur.execute('''
    CREATE TABLE IF NOT EXISTS recipients (
        recipient_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID NOT NULL REFERENCES users(user_id),
        email VARCHAR(255) NOT NULL,
        first_name VARCHAR(255),
        last_name VARCHAR(255),
        company VARCHAR(255),
        position VARCHAR(255),
        custom_fields JSONB,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        is_active BOOLEAN DEFAULT TRUE
    )
    ''')
    
    # Create campaign_recipients table
    cur.execute('''
    CREATE TABLE IF NOT EXISTS campaign_recipients (
        campaign_recipient_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        campaign_id UUID NOT NULL REFERENCES email_campaigns(campaign_id),
        recipient_id UUID NOT NULL REFERENCES recipients(recipient_id),
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        is_active BOOLEAN DEFAULT TRUE,
        CONSTRAINT unique_campaign_recipient UNIQUE (campaign_id, recipient_id)
    )
    ''')
    
    # Create email_tracking table
    cur.execute('''
    CREATE TABLE IF NOT EXISTS email_tracking (
        tracking_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        campaign_id UUID NOT NULL REFERENCES email_campaigns(campaign_id),
        recipient_id UUID NOT NULL REFERENCES recipients(recipient_id),
        email_status VARCHAR(50) DEFAULT 'pending',
        sent_at TIMESTAMP WITH TIME ZONE,
        delivered_at TIMESTAMP WITH TIME ZONE,
        opened_at TIMESTAMP WITH TIME ZONE,
        clicked_at TIMESTAMP WITH TIME ZONE,
        replied_at TIMESTAMP WITH TIME ZONE,
        bounced_at TIMESTAMP WITH TIME ZONE,
        tracking_pixel_id VARCHAR(255) UNIQUE,
        open_count INTEGER DEFAULT 0,
        click_count INTEGER DEFAULT 0,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        is_active BOOLEAN DEFAULT TRUE
    )
    ''')
    
    # Create url_tracking table
    cur.execute('''
    CREATE TABLE IF NOT EXISTS url_tracking (
        url_tracking_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tracking_id UUID NOT NULL REFERENCES email_tracking(tracking_id),
        original_url TEXT NOT NULL,
        tracking_url TEXT NOT NULL,
        click_count INTEGER DEFAULT 0,
        first_clicked_at TIMESTAMP WITH TIME ZONE,
        last_clicked_at TIMESTAMP WITH TIME ZONE,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        is_active BOOLEAN DEFAULT TRUE
    )
    ''')
    
    conn.commit()
    current_app.logger.info("Database tables initialized")

# ==================== USER MODEL ====================
class UserModel:
    def find_by_email(self, email):
        """Find a user by email address"""
        conn, cur = get_db_connection()
        cur.execute("SELECT * FROM users WHERE email = %s", (email,))
        return cur.fetchone()
    
    def create(self, email, password_hash, full_name):
        """Create a new user"""
        conn, cur = get_db_connection()
        cur.execute("""
            INSERT INTO users (email, password_hash, full_name)
            VALUES (%s, %s, %s)
            RETURNING user_id, email, full_name
        """, (email, password_hash, full_name))
        
        return cur.fetchone()

# ==================== CAMPAIGN MODEL ====================
class CampaignModel:
    def get_all_by_user(self, user_id):
        """Get all campaigns for a user"""
        conn, cur = get_db_connection()
        cur.execute("""
            SELECT * FROM email_campaigns
            WHERE user_id = %s AND is_active = TRUE
            ORDER BY created_at DESC
        """, (user_id,))
        return cur.fetchall()
    
    def count_recipients(self, campaign_id):
        """Count recipients for a campaign"""
        conn, cur = get_db_connection()
        cur.execute("""
            SELECT COUNT(*) as recipient_count FROM campaign_recipients
            WHERE campaign_id = %s AND is_active = TRUE
        """, (campaign_id,))
        return cur.fetchone()['recipient_count']
    
    def get_tracking_stats(self, campaign_id):
        """Get tracking statistics for a campaign"""
        conn, cur = get_db_connection()
        cur.execute("""
            SELECT 
                COUNT(*) FILTER (WHERE sent_at IS NOT NULL) as sent_count,
                COUNT(*) FILTER (WHERE opened_at IS NOT NULL) as opened_count,
                COUNT(*) FILTER (WHERE clicked_at IS NOT NULL) as clicked_count,
                COUNT(*) FILTER (WHERE replied_at IS NOT NULL) as replied_count
            FROM email_tracking
            WHERE campaign_id = %s
        """, (campaign_id,))
        return cur.fetchone()
    
    def create(self, user_id, campaign_name, subject_line, from_name, from_email, reply_to_email):
        """Create a new campaign"""
        conn, cur = get_db_connection()
        cur.execute("""
            INSERT INTO email_campaigns 
            (user_id, campaign_name, subject_line, from_name, from_email, reply_to_email)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING campaign_id
        """, (
            user_id, 
            campaign_name, 
            subject_line, 
            from_name,
            from_email,
            reply_to_email
        ))
        
        campaign = cur.fetchone()
        return campaign['campaign_id']
    
    def add_recipient(self, campaign_id, recipient_id):
        """Add a recipient to a campaign"""
        conn, cur = get_db_connection()
        cur.execute("""
            INSERT INTO campaign_recipients (campaign_id, recipient_id)
            VALUES (%s, %s)
            ON CONFLICT (campaign_id, recipient_id) DO NOTHING
        """, (campaign_id, recipient_id))
    
    def find_by_id(self, campaign_id, user_id):
        """Find a campaign by ID and verify ownership"""
        conn, cur = get_db_connection()
        cur.execute("""
            SELECT * FROM email_campaigns
            WHERE campaign_id = %s AND user_id = %s
        """, (campaign_id, user_id))
        return cur.fetchone()
    
    def get_recipients(self, campaign_id):
        """Get all recipients for a campaign"""
        conn, cur = get_db_connection()
        cur.execute("""
            SELECT r.* FROM recipients r
            JOIN campaign_recipients cr ON r.recipient_id = cr.recipient_id
            WHERE cr.campaign_id = %s AND cr.is_active = TRUE AND r.is_active = TRUE
        """, (campaign_id,))
        return cur.fetchall()
    
    def update_status(self, campaign_id, status):
        """Update campaign status"""
        conn, cur = get_db_connection()
        cur.execute("""
            UPDATE email_campaigns
            SET status = %s
            WHERE campaign_id = %s
        """, (status, campaign_id))
        conn.commit()
    
    def count_by_user(self, user_id):
        """Count campaigns for a user"""
        conn, cur = get_db_connection()
        cur.execute("""
            SELECT COUNT(*) as campaign_count
            FROM email_campaigns
            WHERE user_id = %s AND is_active = TRUE
        """, (user_id,))
        return cur.fetchone()['campaign_count']
    
    def get_completed_by_user(self, user_id):
        """Get completed campaigns for a user"""
        conn, cur = get_db_connection()
        cur.execute("""
            SELECT * FROM email_campaigns
            WHERE user_id = %s AND status = 'completed' AND is_active = TRUE
            ORDER BY sent_at DESC
        """, (user_id,))
        return cur.fetchall()
    
    def get_recent_by_user(self, user_id, limit=5):
        """Get recent campaigns for a user"""
        conn, cur = get_db_connection()
        cur.execute("""
            SELECT * FROM email_campaigns
            WHERE user_id = %s AND is_active = TRUE
            ORDER BY created_at DESC
            LIMIT %s
        """, (user_id, limit))
        return cur.fetchall()
    
    def mark_as_completed(self, campaign_id):
        """Mark a campaign as completed"""
        conn, cur = get_db_connection()
        cur.execute("""
            UPDATE email_campaigns
            SET status = 'completed', sent_at = NOW()
            WHERE campaign_id = %s
        """, (campaign_id,))
        conn.commit()

# ==================== RECIPIENT MODEL ====================
class RecipientModel:
    def get_all_by_user(self, user_id):
        """Get all recipients for a user"""
        conn, cur = get_db_connection()
        cur.execute("""
            SELECT * FROM recipients
            WHERE user_id = %s AND is_active = TRUE
            ORDER BY created_at DESC
        """, (user_id,))
        return cur.fetchall()
    
    def find_by_email(self, user_id, email):
        """Find a recipient by email for a specific user"""
        conn, cur = get_db_connection()
        cur.execute("""
            SELECT * FROM recipients
            WHERE user_id = %s AND email = %s AND is_active = TRUE
        """, (user_id, email))
        return cur.fetchone()
    
    def find_by_email_excluding(self, user_id, email, recipient_id):
        """Find a recipient by email, excluding a specific recipient_id"""
        conn, cur = get_db_connection()
        cur.execute("""
            SELECT * FROM recipients
            WHERE user_id = %s AND email = %s AND recipient_id != %s AND is_active = TRUE
        """, (user_id, email, recipient_id))
        return cur.fetchone()
    
    def create(self, user_id, email, first_name, last_name, company, position, custom_fields):
        """Create a new recipient"""
        conn, cur = get_db_connection()
        cur.execute("""
            INSERT INTO recipients 
            (user_id, email, first_name, last_name, company, position, custom_fields)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING recipient_id
        """, (
            user_id,
            email,
            first_name,
            last_name,
            company,
            position,
            custom_fields
        ))
        
        recipient = cur.fetchone()
        return recipient['recipient_id']
    
    def find_by_id(self, recipient_id, user_id):
        """Find a recipient by ID and verify ownership"""
        conn, cur = get_db_connection()
        cur.execute("""
            SELECT * FROM recipients
            WHERE recipient_id = %s AND user_id = %s AND is_active = TRUE
        """, (recipient_id, user_id))
        return cur.fetchone()
    
    def update(self, recipient_id, email, first_name, last_name, company, position, custom_fields):
        """Update an existing recipient"""
        conn, cur = get_db_connection()
        cur.execute("""
            UPDATE recipients
            SET 
                email = %s,
                first_name = %s,
                last_name = %s,
                company = %s,
                position = %s,
                custom_fields = %s,
                updated_at = NOW()
            WHERE recipient_id = %s
            RETURNING recipient_id
        """, (
            email,
            first_name,
            last_name,
            company,
            position,
            custom_fields,
            recipient_id
        ))
        
        updated = cur.fetchone()
        return updated['recipient_id']
    
    def soft_delete(self, recipient_id):
        """Soft delete a recipient"""
        conn, cur = get_db_connection()
        cur.execute("""
            UPDATE recipients
            SET is_active = FALSE, updated_at = NOW()
            WHERE recipient_id = %s
        """, (recipient_id,))
    
    def remove_from_campaigns(self, recipient_id):
        """Remove a recipient from all campaigns"""
        conn, cur = get_db_connection()
        cur.execute("""
            UPDATE campaign_recipients
            SET is_active = FALSE
            WHERE recipient_id = %s
        """, (recipient_id,))
    
    def validate_ownership(self, user_id, recipient_ids):
        """Validate that a list of recipient IDs belong to a user"""
        conn, cur = get_db_connection()
        placeholders = ','.join(['%s'] * len(recipient_ids))
        query_params = recipient_ids + [user_id]
        
        cur.execute(f"""
            SELECT recipient_id FROM recipients
            WHERE recipient_id IN ({placeholders})
            AND user_id = %s
        """, query_params)
        
        return [str(row['recipient_id']) for row in cur.fetchall()]
    
    def soft_delete_bulk(self, recipient_ids):
        """Soft delete multiple recipients"""
        conn, cur = get_db_connection()
        placeholders = ','.join(['%s'] * len(recipient_ids))
        
        cur.execute(f"""
            UPDATE recipients
            SET is_active = FALSE, updated_at = NOW()
            WHERE recipient_id IN ({placeholders})
        """, recipient_ids)
    
    def remove_bulk_from_campaigns(self, recipient_ids):
        """Remove multiple recipients from all campaigns"""
        conn, cur = get_db_connection()
        placeholders = ','.join(['%s'] * len(recipient_ids))
        
        cur.execute(f"""
            UPDATE campaign_recipients
            SET is_active = FALSE
            WHERE recipient_id IN ({placeholders})
        """, recipient_ids)
    
    def count_by_user(self, user_id):
        """Count recipients for a user"""
        conn, cur = get_db_connection()
        cur.execute("""
            SELECT COUNT(*) as recipient_count
            FROM recipients
            WHERE user_id = %s AND is_active = TRUE
        """, (user_id,))
        return cur.fetchone()['recipient_count']
    
    def get_recent_by_user(self, user_id, limit=5):
        """Get recent recipients for a user"""
        conn, cur = get_db_connection()
        cur.execute("""
            SELECT * FROM recipients
            WHERE user_id = %s AND is_active = TRUE
            ORDER BY created_at DESC
            LIMIT %s
        """, (user_id, limit))
        return cur.fetchall()

# ==================== TEMPLATE MODEL ====================
class TemplateModel:
    def get_all_by_user(self, user_id):
        """Get all templates for a user"""
        conn, cur = get_db_connection()
        cur.execute("""
            SELECT * FROM email_templates
            WHERE user_id = %s AND is_active = TRUE
            ORDER BY created_at DESC
        """, (user_id,))
        return cur.fetchall()
    
    def create(self, user_id, campaign_id, template_name, html_content, text_content):
        """Create a new template"""
        conn, cur = get_db_connection()
        cur.execute("""
            INSERT INTO email_templates
            (user_id, campaign_id, template_name, html_content, text_content)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING template_id
        """, (user_id, campaign_id, template_name, html_content, text_content))
        template = cur.fetchone()
        return template['template_id']
    
    def find_by_campaign_id(self, campaign_id):
        """Find a template by campaign ID"""
        conn, cur = get_db_connection()
        cur.execute("""
            SELECT * FROM email_templates
            WHERE campaign_id = %s AND is_active = TRUE
            LIMIT 1
        """, (campaign_id,))
        return cur.fetchone()
    
    def count_by_user(self, user_id):
        """Count templates for a user"""
        conn, cur = get_db_connection()
        cur.execute("""
            SELECT COUNT(*) as template_count
            FROM email_templates
            WHERE user_id = %s AND is_active = TRUE
        """, (user_id,))
        return cur.fetchone()['template_count']


# ==================== TRACKING MODEL ====================
class TrackingModel:
    def create_tracking_entry(self, campaign_id, recipient_id, tracking_pixel_id, status='sending'):
        """Create a new tracking entry"""
        conn, cur = get_db_connection()
        cur.execute("""
            INSERT INTO email_tracking 
            (campaign_id, recipient_id, tracking_pixel_id, email_status)
            VALUES (%s, %s, %s, %s)
            RETURNING tracking_id
        """, (campaign_id, recipient_id, tracking_pixel_id, status))
        tracking = cur.fetchone()
        conn.commit()
        return tracking
    
    def update_tracking_status(self, tracking_id, status, timestamp_field=None):
        """Update tracking status and timestamp"""
        conn, cur = get_db_connection()
        if timestamp_field:
            # Update both status and specific timestamp field
            cur.execute(f"""
                UPDATE email_tracking
                SET 
                    email_status = %s,
                    {timestamp_field} = COALESCE({timestamp_field}, NOW()),
                    updated_at = NOW()
                WHERE tracking_id = %s
                RETURNING tracking_id
            """, (status, tracking_id))
        else:
            # Update only status
            cur.execute("""
                UPDATE email_tracking
                SET 
                    email_status = %s,
                    updated_at = NOW()
                WHERE tracking_id = %s
                RETURNING tracking_id
            """, (status, tracking_id))
        
        updated = cur.fetchone()
        conn.commit()
        return updated
    
    def find_by_pixel_id(self, tracking_pixel_id):
        """Find tracking by pixel ID"""
        conn, cur = get_db_connection()
        cur.execute("""
            SELECT tracking_id, email_status, opened_at, open_count 
            FROM email_tracking
            WHERE tracking_pixel_id = %s
        """, (tracking_pixel_id,))
        return cur.fetchone()
    
    def record_open(self, tracking_pixel_id):
        """Record an email open event"""
        conn = None
        try:
            conn = get_direct_db_connection()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            
            # Find tracking entry
            cur.execute("""
                SELECT tracking_id, email_status, opened_at, open_count 
                FROM email_tracking
                WHERE tracking_pixel_id = %s
            """, (tracking_pixel_id,))
            
            tracking = cur.fetchone()
            
            if tracking:
                current_app.logger.info(f"✅ Found tracking entry: {tracking['tracking_id']}")
                current_app.logger.info(f"Current values: status={tracking['email_status']}, opened_at={tracking['opened_at']}, count={tracking['open_count']}")
                
                # Update tracking data - don't downgrade from 'clicked' to 'opened'
                cur.execute("""
                    UPDATE email_tracking
                    SET 
                        email_status = CASE
                            WHEN email_status IN ('sending', 'sent', 'pending') THEN 'opened'
                            ELSE email_status -- Keep existing status if it's 'clicked' or 'replied'
                        END,
                        opened_at = COALESCE(opened_at, NOW()),
                        open_count = open_count + 1,
                        updated_at = NOW()
                    WHERE tracking_id = %s
                    RETURNING tracking_id, email_status, opened_at, open_count, updated_at
                """, (tracking['tracking_id'],))
                
                updated = cur.fetchone()
                
                # Explicitly commit and confirm
                conn.commit()
                current_app.logger.info(f"✅ UPDATE COMMITTED: status={updated['email_status']}, opened_at={updated['opened_at']}, count={updated['open_count']}")
                
                # Double-check the update
                cur.execute("""
                    SELECT tracking_id, email_status, opened_at, open_count 
                    FROM email_tracking
                    WHERE tracking_id = %s
                """, (tracking['tracking_id'],))
                
                verification = cur.fetchone()
                current_app.logger.info(f"✅ VERIFIED VALUES: status={verification['email_status']}, opened_at={verification['opened_at']}, count={verification['open_count']}")
                
            else:
                current_app.logger.warning(f"⚠️ No tracking entry found for pixel ID: {tracking_pixel_id}")
            
            # Return a 1x1 transparent pixel
            pixel = base64.b64decode('R0lGODlhAQABAIAAAP///wAAACH5BAEAAAAALAAAAAABAAEAAAICRAEAOw==')
            
            return {'pixel': pixel}
        
        except Exception as e:
            current_app.logger.error(f"❌ Error tracking open: {str(e)}")
            if conn:
                try:
                    conn.rollback()
                except:
                    pass
            
            # Return a transparent pixel anyway
            pixel = base64.b64decode('R0lGODlhAQABAIAAAP///wAAACH5BAEAAAAALAAAAAABAAEAAAICRAEAOw==')
            return {'pixel': pixel}
        finally:
            if conn:
                conn.close()
    
    def get_fallback_pixel(self):
        """Get a transparent pixel for fallback return"""
        return base64.b64decode('R0lGODlhAQABAIAAAP///wAAACH5BAEAAAAALAAAAAABAAEAAAICRAEAOw==')
    
    def find_url_tracking(self, url_tracking_id):
        """Find URL tracking by ID"""
        conn, cur = get_db_connection()
        cur.execute("""
            SELECT * FROM url_tracking
            WHERE url_tracking_id = %s
        """, (url_tracking_id,))
        return cur.fetchone()
    
    def record_click(self, tracking_id, url_tracking_id):
        """Record an email click event"""
        conn = None
        try:
            conn = get_direct_db_connection()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            
            # Find url tracking entry
            cur.execute("""
                SELECT * FROM url_tracking
                WHERE url_tracking_id = %s
            """, (url_tracking_id,))
            
            url_tracking = cur.fetchone()
            
            if not url_tracking:
                current_app.logger.warning(f"⚠️ No URL tracking entry found for {url_tracking_id}")
                return None
                
            original_url = url_tracking['original_url']
            current_app.logger.info(f"✅ Found original URL: {original_url}")
            
            # Update url tracking data
            cur.execute("""
                UPDATE url_tracking
                SET 
                    click_count = click_count + 1,
                    first_clicked_at = COALESCE(first_clicked_at, NOW()),
                    last_clicked_at = NOW()
                WHERE url_tracking_id = %s
                RETURNING url_tracking_id, click_count
            """, (url_tracking_id,))
            
            url_update = cur.fetchone()
            current_app.logger.info(f"✅ Updated URL tracking: url_id={url_update['url_tracking_id']}, clicks={url_update['click_count']}")
            
            # First check if this tracking ID exists and get its current values
            cur.execute("""
                SELECT tracking_id, email_status, opened_at, open_count, clicked_at, click_count, replied_at
                FROM email_tracking
                WHERE tracking_id = %s
            """, (tracking_id,))
            
            tracking = cur.fetchone()
            
            if tracking:
                current_app.logger.info(f"✅ Found tracking entry: {tracking['tracking_id']}")
                current_app.logger.info(f"Current values: status={tracking['email_status']}, opened_at={tracking['opened_at']}, open_count={tracking['open_count']}, clicked_at={tracking['clicked_at']}, click_count={tracking['click_count']}")
                
                # Update email tracking - ensure opened is also recorded
                cur.execute("""
                    UPDATE email_tracking
                    SET 
                        -- Set status to 'clicked' unless it's already 'replied'
                        email_status = CASE
                            WHEN email_status = 'replied' THEN 'replied'
                            ELSE 'clicked'
                        END,
                        -- Always ensure opened_at is set - clicking means they opened it
                        opened_at = COALESCE(opened_at, NOW()),
                        -- Make sure open_count is at least 1
                        open_count = CASE WHEN open_count = 0 THEN 1 ELSE open_count END,
                        -- Update clicked data
                        clicked_at = COALESCE(clicked_at, NOW()),
                        click_count = click_count + 1,
                        updated_at = NOW()
                    WHERE tracking_id = %s
                    RETURNING tracking_id, email_status, opened_at, open_count, clicked_at, click_count
                """, (tracking_id,))
                
                tracking_update = cur.fetchone()
                
                conn.commit()
                current_app.logger.info(f"✅ UPDATE COMMITTED: status={tracking_update['email_status']}, opened_at={tracking_update['opened_at']}, open_count={tracking_update['open_count']}, clicked_at={tracking_update['clicked_at']}, click_count={tracking_update['click_count']}")
                
                # Double-check the update
                cur.execute("""
                    SELECT tracking_id, email_status, opened_at, open_count, clicked_at, click_count
                    FROM email_tracking
                    WHERE tracking_id = %s
                """, (tracking_id,))
                
                verification = cur.fetchone()
                current_app.logger.info(f"✅ VERIFIED VALUES: status={verification['email_status']}, opens={verification['open_count']}, clicks={verification['click_count']}")
            else:
                current_app.logger.warning(f"⚠️ No email tracking record found for {tracking_id}")
                conn.commit()
            
            current_app.logger.info(f"🔄 Redirecting to: {original_url}")
            
            return {'original_url': original_url}
            
        except Exception as e:
            current_app.logger.error(f"❌ Error tracking click: {str(e)}")
            if conn:
                try:
                    conn.rollback()
                except:
                    pass
            return None
        finally:
            if conn:
                conn.close()
    
    def record_beacon(self, tracking_pixel_id):
        """Record a JavaScript beacon tracking event"""
        conn = None
        try:
            conn = get_direct_db_connection()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            
            # Find tracking entry
            cur.execute("""
                SELECT tracking_id, email_status, opened_at, open_count 
                FROM email_tracking
                WHERE tracking_pixel_id = %s
            """, (tracking_pixel_id,))
            
            tracking = cur.fetchone()
            
            if tracking:
                current_app.logger.info(f"✅ Found tracking entry for beacon: {tracking['tracking_id']}")
                
                # Update tracking data - similar to track_open
                cur.execute("""
                    UPDATE email_tracking
                    SET 
                        email_status = CASE
                            WHEN email_status IN ('sending', 'sent', 'pending') THEN 'opened'
                            ELSE email_status
                        END,
                        opened_at = COALESCE(opened_at, NOW()),
                        open_count = open_count + 1,
                        updated_at = NOW()
                    WHERE tracking_id = %s
                    RETURNING tracking_id, email_status, opened_at, open_count
                """, (tracking['tracking_id'],))
                
                updated = cur.fetchone()
                conn.commit()
                current_app.logger.info(f"✅ Beacon tracking updated: status={updated['email_status']}, opens={updated['open_count']}")
                return True
            else:
                current_app.logger.warning(f"⚠️ No tracking entry found for beacon ID: {tracking_pixel_id}")
                return False
        
        except Exception as e:
            current_app.logger.error(f"❌ Error tracking beacon: {str(e)}")
            if conn:
                try:
                    conn.rollback()
                except:
                    pass
            return False
        finally:
            if conn:
                conn.close()
    
    def mark_as_replied(self, campaign_id, recipient_id):
        """Mark an email as replied"""
        conn = None
        try:
            conn = get_direct_db_connection()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            
            # Update tracking record
            cur.execute("""
                UPDATE email_tracking
                SET 
                    email_status = 'replied',
                    replied_at = COALESCE(replied_at, NOW()),
                    updated_at = NOW()
                WHERE campaign_id = %s AND recipient_id = %s
                RETURNING tracking_id, replied_at
            """, (campaign_id, recipient_id))
            
            result = cur.fetchone()
            
            if not result:
                return None
            
            # Explicitly commit the transaction
            conn.commit()
            
            return result
        except Exception as e:
            current_app.logger.error(f"Error marking email as replied: {str(e)}")
            if conn:
                conn.rollback()
            return None
        finally:
            if conn:
                conn.close()
    
    def get_by_campaign(self, campaign_id):
        """Get all tracking entries for a campaign with recipient details"""
        conn, cur = get_db_connection()
        cur.execute("""
            SELECT et.*, r.email, r.first_name, r.last_name 
            FROM email_tracking et
            JOIN recipients r ON et.recipient_id = r.recipient_id
            WHERE et.campaign_id = %s
        """, (campaign_id,))
        return cur.fetchall()
    
    def get_debug_data(self, campaign_id):
        """Get tracking data for debugging"""
        conn, cur = get_db_connection()
        
        # Get raw tracking data from database
        cur.execute("""
            SELECT 
                et.tracking_id, 
                et.recipient_id, 
                r.email as recipient_email,
                et.email_status,
                et.sent_at,
                et.opened_at,
                et.clicked_at,
                et.replied_at,
                et.open_count,
                et.click_count,
                et.tracking_pixel_id,
                et.created_at,
                et.updated_at
            FROM email_tracking et
            JOIN recipients r ON et.recipient_id = r.recipient_id
            WHERE et.campaign_id = %s
        """, (campaign_id,))
        
        tracking_data = []
        for row in cur.fetchall():
            data = dict(row)
            # Format UUIDs
            data['tracking_id'] = str(data['tracking_id'])
            data['recipient_id'] = str(data['recipient_id'])
            
            # Format dates
            for key in ['sent_at', 'opened_at', 'clicked_at', 'replied_at', 'created_at', 'updated_at']:
                if key in data and data[key]:
                    data[key] = data[key].isoformat()
            
            # Add testing links
            data['test_links'] = {
                'open_url': f"/track/open/{data['tracking_pixel_id']}",
                'beacon_url': f"/track/beacon/{data['tracking_pixel_id']}",
                'click_test': f"/api/debug/test-click/{data['tracking_id']}"
            }
            
            tracking_data.append(data)
        
        return tracking_data
    
    def get_debug_url_data(self, campaign_id):
        """Get URL tracking data for debugging"""
        conn, cur = get_db_connection()
        
        # Get URL tracking data
        cur.execute("""
            SELECT ut.* 
            FROM url_tracking ut
            JOIN email_tracking et ON ut.tracking_id = et.tracking_id
            WHERE et.campaign_id = %s
            ORDER BY ut.created_at DESC
        """, (campaign_id,))
        
        url_data = []
        for row in cur.fetchall():
            data = dict(row)
            # Format UUIDs
            data['url_tracking_id'] = str(data['url_tracking_id'])
            data['tracking_id'] = str(data['tracking_id'])
            
            # Format dates
            for key in ['first_clicked_at', 'last_clicked_at', 'created_at']:
                if key in data and data[key]:
                    data[key] = data[key].isoformat()
            
            # Add the actual tracking URL
            data['click_test_url'] = f"/track/click/{data['tracking_id']}/{data['url_tracking_id']}"
            
            url_data.append(data)
        
        return url_data
    
    def manual_record_open(self, campaign_id, recipient_id):
        """Manually record an open event for debugging"""
        conn = None
        try:
            conn = get_direct_db_connection()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            
            # Find tracking entry
            cur.execute("""
                SELECT * FROM email_tracking
                WHERE campaign_id = %s AND recipient_id = %s
            """, (campaign_id, recipient_id))
            
            tracking = cur.fetchone()
            
            if tracking:
                # Update tracking data
                cur.execute("""
                    UPDATE email_tracking
                    SET 
                        email_status = 'opened',
                        opened_at = COALESCE(opened_at, NOW()),
                        open_count = open_count + 1,
                        updated_at = NOW()
                    WHERE tracking_id = %s
                    RETURNING tracking_id, opened_at, open_count
                """, (tracking['tracking_id'],))
                
                updated = cur.fetchone()
                conn.commit()
                
                result = {
                    'tracking_id': updated['tracking_id'],
                    'opened_at': updated['opened_at'],
                    'open_count': updated['open_count']
                }
                
                return result
            else:
                return None
        except Exception as e:
            if conn:
                conn.rollback()
            raise e
        finally:
            if conn:
                conn.close()
    
    def create_test_click(self, tracking_id):
        """Create a test URL tracking entry for debugging"""
        conn = None
        try:
            conn = get_direct_db_connection()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            
            # Create a test URL tracking entry
            cur.execute("""
                INSERT INTO url_tracking
                (tracking_id, original_url, tracking_url, click_count)
                VALUES (%s, %s, %s, 0)
                RETURNING url_tracking_id
            """, (tracking_id, 'https://www.google.com', f'http://localhost:5000/track/click/{tracking_id}/test'))
            
            url_tracking_id = cur.fetchone()['url_tracking_id']
            conn.commit()
            
            return {'url_tracking_id': url_tracking_id}
            
        except Exception as e:
            if conn:
                conn.rollback()
            return None
        finally:
            if conn:
                conn.close()


# Initialize model instances
user_model = UserModel()
campaign_model = CampaignModel()
recipient_model = RecipientModel()
template_model = TemplateModel()
tracking_model = TrackingModel()