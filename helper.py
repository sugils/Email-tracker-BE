"""
Helper module with utility functions for the Email Campaign Management API.
Contains shared functions used across multiple modules.
"""
from flask import g, current_app
import psycopg2
import psycopg2.extras
import functools
import uuid
import base64
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from bs4 import BeautifulSoup
import imaplib
import email
from email.header import decode_header
from datetime import datetime, timedelta

# Email and SMTP Configuration - better to use environment variables in production
SMTP_SERVER = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
SMTP_PORT = int(os.environ.get('SMTP_PORT', '587'))
SMTP_USERNAME = os.environ.get('SMTP_USERNAME', 'sugil.s@vdartinc.com')
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', 'elka vboz rmvq lucw')

# Base URL for your application - used for tracking links
BASE_URL = os.environ.get('BASE_URL', 'http://localhost:5000/')

# Database Configuration - better to use environment variables in production
DB_HOST = os.environ.get('DB_HOST', 'localhost')
DB_PORT = os.environ.get('DB_PORT', '5432')
DB_NAME = os.environ.get('DB_NAME', 'email_app')
DB_USER = os.environ.get('DB_USER', 'postgres')
DB_PASS = os.environ.get('DB_PASS', 'Admin@123')

# ==================== DATABASE CONNECTION FUNCTIONS ====================
def get_db_connection():
    """Get PostgreSQL database connection using Flask's g object for request scoping"""
    if 'db' not in g:
        g.db = psycopg2.connect(
            host=DB_HOST,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASS
        )
        g.db.autocommit = False
        # Set cursor factory to return dictionaries
        g.cursor = g.db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    return g.db, g.cursor

def get_direct_db_connection():
    """Get a direct database connection (not tied to Flask's g)
    Use this for background threads or scheduled tasks"""
    conn = psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASS
    )
    conn.autocommit = False
    return conn

def close_db_connection(exception):
    """Close database connection at the end of request"""
    db = g.pop('db', None)
    if db is not None:
        g.pop('cursor', None)
        db.close()

# ==================== DATA CONVERSION HELPERS ====================
def to_dict(row):
    """Convert a database row to a dictionary"""
    if row is None:
        return None
    return dict(row)

def to_list(rows):
    """Convert database rows to a list of dictionaries"""
    return [dict(row) for row in rows]

# ==================== TRANSACTION HANDLING ====================
def handle_transaction(func):
    """Decorator to handle database transactions and rollbacks"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        conn, cur = get_db_connection()
        try:
            result = func(*args, **kwargs)
            conn.commit()
            return result
        except Exception as e:
            conn.rollback()
            current_app.logger.error(f"Database error: {str(e)}")
            return {'error': str(e)}, 500
    return wrapper

# ==================== EMAIL CONTENT PROCESSING ====================
def rewrite_links(html_content, tracking_id, base_url):
    """Replace all links in HTML content with tracking links"""
    current_app.logger.info(f"🔗 Rewriting links for tracking_id: {tracking_id}")
    soup = BeautifulSoup(html_content, 'html.parser')
    conn = None
    
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASS
        )
        conn.autocommit = False
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        link_count = 0
        # Find all links
        for a_tag in soup.find_all('a', href=True):
            original_url = a_tag['href']
            
            # Skip mailto: links, anchors, and javascript: links
            if original_url.startswith('mailto:') or original_url.startswith('#') or original_url.startswith('javascript:'):
                continue
                
            # Create a unique ID for this link
            url_tracking_id = str(uuid.uuid4())
            
            # Create tracking URL
            tracking_url = f"{base_url}track/click/{tracking_id}/{url_tracking_id}"
            
            # Insert into url_tracking table
            cur.execute("""
                INSERT INTO url_tracking
                (tracking_id, original_url, tracking_url, click_count)
                VALUES (%s, %s, %s, 0)
                RETURNING url_tracking_id
            """, (tracking_id, original_url, tracking_url))
            
            # Get the inserted ID
            db_url_id = cur.fetchone()['url_tracking_id']
            
            # Update tracking URL with actual ID from database
            tracking_url = f"{base_url}track/click/{tracking_id}/{db_url_id}"
            
            # Replace the href attribute
            a_tag['href'] = tracking_url
            link_count += 1
            
        # Commit all the URL tracking entries
        conn.commit()
        current_app.logger.info(f"✅ Rewrote {link_count} links for tracking_id: {tracking_id}")
        
        # Add JavaScript beacon tracking as a backup for image blocking
        # This only works if the email client allows JavaScript
        js_beacon = soup.new_tag('script')
        js_beacon.string = f"""
            (function() {{
                try {{
                    setTimeout(function() {{
                        var img = new Image();
                        img.onload = function() {{ /* loaded */ }};
                        img.onerror = function() {{ /* error */ }};
                        img.src = '{base_url}track/beacon/{tracking_id}?t=' + new Date().getTime();
                    }}, 1000);
                }} catch(e) {{
                    // Silently fail if JS is blocked
                }}
            }})();
        """
        
        # Add the beacon script to the body
        if soup.body:
            soup.body.append(js_beacon)
        
        # Return the modified HTML
        return str(soup)
        
    except Exception as e:
        current_app.logger.error(f"❌ Error rewriting links: {str(e)}")
        if conn:
            conn.rollback()
        # If there's an error, return the original HTML
        return html_content
    finally:
        if conn:
            conn.close()

# ==================== EMAIL SENDING FUNCTIONS ====================
def send_email_async(campaign_id, test_mode=False, base_url=None):
    """Asynchronously send emails for a campaign"""
    # Create a new app context for the thread
    with current_app.app_context():
        # Use a direct connection instead of Flask's g since this runs in a background thread
        conn = None
        try:
            # Get public URL for tracking
            if not base_url:
                base_url = os.environ.get('BASE_URL', 'http://localhost:5000/')
                if not base_url.endswith('/'):
                    base_url += '/'
            
            current_app.logger.info(f"📧 Starting email sending for campaign {campaign_id}, test_mode={test_mode}, base_url={base_url}")
            
            conn = psycopg2.connect(
                host=DB_HOST,
                database=DB_NAME,
                user=DB_USER,
                password=DB_PASS
            )
            conn.autocommit = False
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            
            # Get campaign details
            cur.execute("""
                SELECT * FROM email_campaigns WHERE campaign_id = %s
            """, (campaign_id,))
            campaign = cur.fetchone()
            
            if not campaign:
                current_app.logger.error(f"❌ Campaign {campaign_id} not found")
                return
            
            # Get template for campaign
            cur.execute("""
                SELECT * FROM email_templates 
                WHERE campaign_id = %s AND is_active = TRUE
                LIMIT 1
            """, (campaign_id,))
            template = cur.fetchone()
            
            if not template:
                current_app.logger.error(f"❌ No active template found for campaign {campaign_id}")
                return
            
            if test_mode:
                # Send only to the campaign owner for testing
                cur.execute("""
                    SELECT * FROM users WHERE user_id = %s
                """, (campaign['user_id'],))
                user = cur.fetchone()
                recipients = [{'email': user['email'], 'recipient_id': None}]
                current_app.logger.info(f"📧 Test mode: Sending to campaign owner {user['email']}")
            else:
                # Get all recipients for this campaign
                cur.execute("""
                    SELECT r.* FROM recipients r
                    JOIN campaign_recipients cr ON r.recipient_id = cr.recipient_id
                    WHERE cr.campaign_id = %s AND cr.is_active = TRUE AND r.is_active = TRUE
                """, (campaign_id,))
                recipients = cur.fetchall()
                current_app.logger.info(f"📧 Sending campaign to {len(recipients)} recipients")
            
            # Email configuration
            smtp_server = SMTP_SERVER
            smtp_port = SMTP_PORT
            smtp_username = SMTP_USERNAME
            smtp_password = SMTP_PASSWORD
            
            # Initialize SMTP server connection
            current_app.logger.info(f"🔌 Connecting to SMTP server {smtp_server}:{smtp_port}")
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.ehlo()
            server.starttls()
            server.login(smtp_username, smtp_password)
            current_app.logger.info("✅ SMTP connection established")
            
            # Track send counts
            success_count = 0
            failure_count = 0
            
            for recipient in recipients:
                try:
                    # Create unique tracking pixel for this email
                    tracking_pixel_id = str(uuid.uuid4())
                    current_app.logger.debug(f"🔍 Created tracking pixel ID: {tracking_pixel_id} for {recipient['email']}")
                    
                    # Create tracking entry
                    if not test_mode:
                        cur.execute("""
                            INSERT INTO email_tracking 
                            (campaign_id, recipient_id, tracking_pixel_id, email_status)
                            VALUES (%s, %s, %s, 'sending')
                            RETURNING tracking_id
                        """, (campaign_id, recipient['recipient_id'], tracking_pixel_id))
                        tracking = cur.fetchone()
                        conn.commit()
                        current_app.logger.debug(f"✅ Created tracking entry: {tracking['tracking_id']}")
                    else:
                        # For test mode, create a temporary tracking ID
                        tracking = {'tracking_id': str(uuid.uuid4())}
                    
                    # Personalize email content
                    html_content = template['html_content']
                    text_content = template.get('text_content', '')
                    
                    if not test_mode and recipient.get('first_name'):
                        html_content = html_content.replace('{{first_name}}', recipient['first_name'])
                        text_content = text_content.replace('{{first_name}}', recipient['first_name'])
                        if recipient.get('last_name'):
                            html_content = html_content.replace('{{last_name}}', recipient['last_name'])
                            text_content = text_content.replace('{{last_name}}', recipient['last_name'])
                    
                    # Add tracking pixel
                    tracking_pixel_url = f"{base_url}track/open/{tracking_pixel_id}"
                    tracking_pixel = f'<img src="{tracking_pixel_url}" width="1" height="1" alt="" style="display:none" />'
                    
                    # First rewrite links for click tracking
                    if not test_mode:
                        html_content = rewrite_links(html_content, tracking['tracking_id'], base_url)
                    
                    # Add the tracking pixel at the very end
                    html_content = html_content + tracking_pixel
                    
                    # Create email message
                    msg = MIMEMultipart('alternative')
                    msg['Subject'] = campaign['subject_line']
                    msg['From'] = f"{campaign['from_name']} <{campaign['from_email']}>"
                    msg['To'] = recipient['email']
                    msg['Reply-To'] = campaign['reply_to_email']
                    # Add important headers for better deliverability
                    msg['List-Unsubscribe'] = f"<mailto:{campaign['reply_to_email']}?subject=Unsubscribe>"
                    
                    # Add text and HTML parts
                    if text_content:
                        part1 = MIMEText(text_content, 'plain')
                        msg.attach(part1)
                    
                    part2 = MIMEText(html_content, 'html')
                    msg.attach(part2)
                    
                    # Send the email
                    server.send_message(msg)
                    success_count += 1
                    
                    # Log that message was sent
                    current_app.logger.info(f"✅ Email sent to {recipient['email']}")
                    
                    # Update tracking status
                    if not test_mode:
                        cur.execute("""
                            UPDATE email_tracking
                            SET email_status = 'sent', sent_at = NOW(), updated_at = NOW()
                            WHERE tracking_id = %s
                        """, (tracking['tracking_id'],))
                        conn.commit()
                
                except Exception as e:
                    current_app.logger.error(f"❌ Error sending email to {recipient['email']}: {str(e)}")
                    failure_count += 1
                    if not test_mode:
                        try:
                            cur.execute("""
                                UPDATE email_tracking
                                SET email_status = 'failed', updated_at = NOW()
                                WHERE tracking_id = %s
                            """, (tracking['tracking_id'],))
                            conn.commit()
                        except Exception as ex:
                            current_app.logger.error(f"❌ Error updating tracking status: {str(ex)}")
                            conn.rollback()
            
            # Close the SMTP connection
            server.quit()
            current_app.logger.info(f"✅ SMTP connection closed, sent {success_count} emails, {failure_count} failures")
            
            # Update campaign status
            if not test_mode:
                cur.execute("""
                    UPDATE email_campaigns
                    SET status = 'completed', sent_at = NOW()
                    WHERE campaign_id = %s
                """, (campaign_id,))
                conn.commit()
                current_app.logger.info(f"✅ Campaign {campaign_id} marked as completed")
                
        except Exception as e:
            current_app.logger.error(f"❌ Error in send_email_async: {str(e)}")
            if conn:
                conn.rollback()
        finally:
            if conn:
                conn.close()

# ==================== EMAIL REPLY CHECKING ====================
def check_for_replies():
    """Check for email replies and update tracking data"""
    current_app.logger.info("Starting scheduled email reply check")
    
    # Email configuration
    username = SMTP_USERNAME
    password = SMTP_PASSWORD
    imap_server = "imap.gmail.com"  # Use your IMAP server
    
    conn = None
    mail = None
    try:
        # Connect to IMAP server
        current_app.logger.info(f"Connecting to IMAP server: {imap_server}")
        mail = imaplib.IMAP4_SSL(imap_server)
        mail.login(username, password)
        mail.select("INBOX")
        current_app.logger.info("Successfully connected to IMAP server")
        
        # Search for recent emails (last 24 hours)
        date = (datetime.now() - timedelta(days=1)).strftime("%d-%b-%Y")
        status, messages = mail.search(None, f'(SINCE {date})')
        message_ids = messages[0].split(b' ')
        current_app.logger.info(f"Found {len(message_ids)} messages in the last 24 hours")
        
        if not message_ids or message_ids[0] == b'':
            current_app.logger.info("No messages found to check")
            return
        
        conn = psycopg2.connect(
            host=DB_HOST,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASS
        )
        conn.autocommit = False
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Get all campaign subjects for matching
        cur.execute("""
            SELECT campaign_id, subject_line FROM email_campaigns
            WHERE status = 'completed'
        """)
        campaigns = cur.fetchall()
        campaign_subjects = {c['subject_line']: c['campaign_id'] for c in campaigns}
        current_app.logger.info(f"Loaded {len(campaign_subjects)} campaign subjects for matching")
        
        replies_found = 0
        for mail_id in message_ids:
            try:
                current_app.logger.debug(f"Checking message ID: {mail_id}")
                status, msg_data = mail.fetch(mail_id, "(RFC822)")
                
                for response in msg_data:
                    if isinstance(response, tuple):
                        msg = email.message_from_bytes(response[1])
                        subject = decode_header(msg["Subject"])[0][0]
                        sender = msg.get("From", "")
                        
                        # Check if it's a reply (subject starts with Re:)
                        if isinstance(subject, bytes):
                            subject = subject.decode()
                        
                        current_app.logger.debug(f"Processing email - Subject: {subject}, From: {sender}")
                        
                        if subject and subject.lower().startswith("re:"):
                            # Extract original subject by removing "Re: "
                            original_subject = subject[4:].strip()
                            current_app.logger.info(f"Found reply email - Original subject: {original_subject}")
                            
                            # Check if this matches any of our campaigns
                            campaign_id = None
                            for camp_subject, camp_id in campaign_subjects.items():
                                if original_subject.lower() == camp_subject.lower():
                                    campaign_id = camp_id
                                    break
                            
                            if campaign_id:
                                current_app.logger.info(f"Matched reply to campaign ID: {campaign_id}")
                                
                                # Find the recipient email from the sender
                                sender_email = None
                                if '<' in sender and '>' in sender:
                                    # Extract email from format "Name <email@example.com>"
                                    sender_email = sender.split('<')[1].split('>')[0].strip()
                                else:
                                    # Just use the whole sender field
                                    sender_email = sender.strip()
                                
                                current_app.logger.info(f"Extracted sender email: {sender_email}")
                                
                                # Find the recipient in our database
                                cur.execute("""
                                    SELECT r.recipient_id, r.email
                                    FROM recipients r
                                    JOIN campaign_recipients cr ON r.recipient_id = cr.recipient_id
                                    WHERE cr.campaign_id = %s AND r.email = %s
                                """, (campaign_id, sender_email))
                                
                                recipient = cur.fetchone()
                                
                                if recipient:
                                    current_app.logger.info(f"Found matching recipient: {recipient['email']}")
                                    
                                    # Check if already replied
                                    cur.execute("""
                                        SELECT tracking_id FROM email_tracking
                                        WHERE campaign_id = %s AND recipient_id = %s AND replied_at IS NOT NULL
                                    """, (campaign_id, recipient['recipient_id']))
                                    
                                    already_replied = cur.fetchone()
                                    
                                    if already_replied:
                                        current_app.logger.info(f"Recipient {recipient['email']} already marked as replied")
                                    else:
                                        # Update tracking status
                                        cur.execute("""
                                            UPDATE email_tracking
                                            SET 
                                                email_status = 'replied',
                                                replied_at = NOW(),
                                                updated_at = NOW()
                                            WHERE campaign_id = %s AND recipient_id = %s
                                            RETURNING tracking_id
                                        """, (campaign_id, recipient['recipient_id']))
                                        
                                        updated = cur.fetchone()
                                        
                                        if updated:
                                            conn.commit()
                                            current_app.logger.info(f"Successfully marked {recipient['email']} as replied, tracking_id: {updated['tracking_id']}")
                                            replies_found += 1
                                        else:
                                            current_app.logger.warning(f"No tracking entry found for {recipient['email']} in campaign {campaign_id}")
                                else:
                                    current_app.logger.warning(f"No matching recipient found for email: {sender_email}")
                            else:
                                current_app.logger.debug(f"No matching campaign found for subject: {original_subject}")
            except Exception as e:
                current_app.logger.error(f"Error processing email {mail_id}: {str(e)}")
                # Continue to next email
        
        current_app.logger.info(f"Reply check complete. Found and processed {replies_found} new replies.")
    
    except Exception as e:
        current_app.logger.error(f"Error in check_for_replies: {str(e)}")
        if conn:
            conn.rollback()
    finally:
        if mail:
            try:
                mail.close()
                mail.logout()
            except:
                pass
        if conn:
            conn.close()

# Safe wrapper for check_for_replies to use with scheduler
def safe_check_for_replies():
    """Safely run the reply check with error handling for the scheduler"""
    try:
        check_for_replies()
    except Exception as e:
        current_app.logger.error(f"Error in scheduled reply check: {str(e)}")