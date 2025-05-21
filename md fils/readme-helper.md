# helper.py - Detailed Documentation

## Overview

`helper.py` contains utility functions and configurations used throughout the Email Campaign Management API. It provides database connection management, transaction handling, data conversion utilities, email sending functionality, and tracking features.

## Imports and Configuration

```python
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
```

The imports provide functionality for:
- Flask application context
- PostgreSQL database operations
- Function decoration (functools)
- UUID generation for tracking
- Base64 encoding/decoding for images
- Environment variable access
- Email sending via SMTP
- Email composition with MIME
- HTML parsing with BeautifulSoup
- Email checking via IMAP
- Date and time operations

```python
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
```

These constants configure:
1. Email server settings (SMTP for sending, IMAP for checking replies)
2. Base URL for tracking links in emails
3. Database connection parameters

Each setting can be overridden by environment variables, with sensible defaults for development.

## Database Connection Functions

```python
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
```

The `get_db_connection` function:
1. Uses Flask's `g` object to store the database connection per request
2. Creates a new connection if one doesn't exist
3. Sets autocommit to False to allow transaction control
4. Configures the cursor to return results as dictionaries (RealDictCursor)
5. Returns both the connection and cursor

```python
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
```

The `get_direct_db_connection` function:
1. Creates a new connection not tied to Flask's request context
2. Used for background threads and scheduled tasks
3. Returns only the connection (cursor must be created by the caller)

```python
def close_db_connection(exception):
    """Close database connection at the end of request"""
    db = g.pop('db', None)
    if db is not None:
        g.pop('cursor', None)
        db.close()
```

The `close_db_connection` function:
1. Removes the database connection from Flask's `g` object
2. Closes the connection to prevent leaks
3. Called at the end of each request via app.teardown_appcontext

## Data Conversion Helpers

```python
def to_dict(row):
    """Convert a database row to a dictionary"""
    if row is None:
        return None
    return dict(row)

def to_list(rows):
    """Convert database rows to a list of dictionaries"""
    return [dict(row) for row in rows]
```

These utility functions convert database rows to Python dictionaries for easier handling and JSON serialization.

## Transaction Handling

```python
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
```

The `handle_transaction` decorator:
1. Gets a database connection and cursor
2. Calls the decorated function
3. Commits the transaction if successful
4. Rolls back the transaction on error
5. Logs errors and returns a 500 response
6. This centralizes transaction handling across the application

## Email Content Processing

```python
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
```

The `rewrite_links` function:
1. Parses HTML content with BeautifulSoup
2. Creates a direct database connection (not tied to the request)
3. Prepares to modify links for tracking

```python
        link_count = 0
        # Find all links
        for a_tag in soup.find_all('a', href=True):
            original_url = a_tag['href']
            
            # Skip mailto: links, anchors, and javascript: links
            if original_url.startswith('mailto:') or original_url.startswith('#') or original_url.startswith('javascript:'):
                continue
```

This section:
1. Finds all `<a>` tags with href attributes
2. Extracts the original URL
3. Skips non-HTTP links like mailto:, anchors (#), and javascript:

```python
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
```

For each link, this code:
1. Generates a unique tracking ID for the link
2. Creates a tracking URL that includes the email tracking ID and link tracking ID
3. Inserts a record into the url_tracking table
4. Gets the database-generated ID for the tracking record
5. Updates the href attribute to point to the tracking URL
6. Increments the link count

```python
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
```

This section adds a JavaScript beacon for tracking:
1. Creates a script tag with self-executing JavaScript
2. The script loads a tracking image via JavaScript as a backup for pixel tracking
3. Uses setTimeout to delay loading slightly
4. Includes a timestamp parameter to prevent caching
5. Adds error handling to silently fail if JavaScript is blocked
6. Appends the script to the email body

## Email Sending Functions

```python
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
```

The `send_email_async` function:
1. Creates a new Flask application context for the background thread
2. Ensures the base URL has a trailing slash
3. This function is designed to run in a separate thread

```python
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
```

This section:
1. Gets the campaign details from the database
2. Gets the email template associated with the campaign
3. Returns early if campaign or template is not found

```python
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
```

This section:
1. In test mode, sends only to the campaign owner
2. In regular mode, gets all active recipients associated with the campaign
3. Logs the number of recipients

```python
            # Initialize SMTP server connection
            current_app.logger.info(f"🔌 Connecting to SMTP server {smtp_server}:{smtp_port}")
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.ehlo()
            server.starttls()
            server.login(smtp_username, smtp_password)
            current_app.logger.info("✅ SMTP connection established")
```

This section:
1. Connects to the SMTP server
2. Initiates a TLS encrypted session
3. Authenticates with the server
4. Logs the connection status

```python
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
```

For each recipient, this code:
1. Generates a unique tracking pixel ID
2. Creates a tracking record in the database (except in test mode)
3. Commits the transaction to save the tracking entry

```python
                    # Personalize email content
                    html_content = template['html_content']
                    text_content = template.get('text_content', '')
                    
                    if not test_mode and recipient.get('first_name'):
                        html_content = html_content.replace('{{first_name}}', recipient['first_name'])
                        text_content = text_content.replace('{{first_name}}', recipient['first_name'])
                        if recipient.get('last_name'):
                            html_content = html_content.replace('{{last_name}}', recipient['last_name'])
                            text_content = text_content.replace('{{last_name}}', recipient['last_name'])
```

This section:
1. Gets the HTML and text content for the email
2. Personalizes the content by replacing placeholders with recipient information
3. Skip personalization in test mode

```python
                    # Add tracking pixel
                    tracking_pixel_url = f"{base_url}track/open/{tracking_pixel_id}"
                    tracking_pixel = f'<img src="{tracking_pixel_url}" width="1" height="1" alt="" style="display:none" />'
                    
                    # First rewrite links for click tracking
                    if not test_mode:
                        html_content = rewrite_links(html_content, tracking['tracking_id'], base_url)
                    
                    # Add the tracking pixel at the very end
                    html_content = html_content + tracking_pixel
```

This section adds tracking elements:
1. Creates a tracking pixel URL that points to the open tracking endpoint
2. Creates an invisible 1x1 pixel image tag
3. Rewrites all links in the email to track clicks
4. Adds the tracking pixel at the end of the HTML content

```python
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
```

This section creates the email message:
1. Creates a multipart MIME message with alternative formats
2. Sets the subject, from, to, and reply-to headers
3. Adds a List-Unsubscribe header for better deliverability
4. Attaches the text version of the email (if available)
5. Attaches the HTML version of the email

```python
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
```

This section:
1. Sends the email via the SMTP server
2. Increments the success counter
3. Logs the successful send
4. Updates the tracking record to 'sent' status with timestamp
5. Commits the transaction

## Email Reply Checking

```python
def check_for_replies():
    """Check for email replies and update tracking data"""
    current_app.logger.info("Starting scheduled email reply check")
    
    # Email configuration
    username = SMTP_USERNAME
    password = SMTP_PASSWORD
    imap_server = "imap.gmail.com"  # Use your IMAP server
```

The `check_for_replies` function:
1. Logs the start of the reply check process
2. Sets up IMAP connection parameters

```python
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
```

This section:
1. Connects to the IMAP server using SSL
2. Logs in with the provided credentials
3. Selects the INBOX folder
4. Searches for emails received in the last 24 hours
5. Logs the number of messages found

```python
        # Get all campaign subjects for matching
        cur.execute("""
            SELECT campaign_id, subject_line FROM email_campaigns
            WHERE status = 'completed'
        """)
        campaigns = cur.fetchall()
        campaign_subjects = {c['subject_line']: c['campaign_id'] for c in campaigns}
        current_app.logger.info(f"Loaded {len(campaign_subjects)} campaign subjects for matching")
```

This section:
1. Gets all completed campaigns from the database
2. Creates a dictionary that maps subject lines to campaign IDs
3. Used to match replies to the original campaign

```python
        for mail_id in message_ids:
            try:
                current_app.logger.debug(f"Checking message ID: {mail_id}")
                status, msg_data = mail.fetch(mail_id, "(RFC822)")
                
                for response in msg_data:
                    if isinstance(response, tuple):
                        msg = email.message_from_bytes(response[1])
                        subject = decode_header(msg["Subject"])[0][0]
                        sender = msg.get("From", "")
```

For each email message:
1. Fetches the full email content
2. Parses the email message
3. Extracts the subject and sender

```python
                        # Check if it's a reply (subject starts with Re:)
                        if isinstance(subject, bytes):
                            subject = subject.decode()
                        
                        current_app.logger.debug(f"Processing email - Subject: {subject}, From: {sender}")
                        
                        if subject and subject.lower().startswith("re:"):
                            # Extract original subject by removing "Re: "
                            original_subject = subject[4:].strip()
                            current_app.logger.info(f"Found reply email - Original subject: {original_subject}")
```

This section:
1. Handles byte strings by decoding them
2. Checks if the subject starts with "Re:" to identify replies
3. Extracts the original subject by removing the "Re: " prefix

```python
                            # Check if this matches any of our campaigns
                            campaign_id = None
                            for camp_subject, camp_id in campaign_subjects.items():
                                if original_subject.lower() == camp_subject.lower():
                                    campaign_id = camp_id
                                    break
                            
                            if campaign_id:
                                current_app.logger.info(f"Matched reply to campaign ID: {campaign_id}")
```

This section:
1. Checks if the original subject matches any of our campaign subjects
2. Case-insensitive matching to increase success rate
3. Logs when a match is found

```python
                                # Find the recipient email from the sender
                                sender_email = None
                                if '<' in sender and '>' in sender:
                                    # Extract email from format "Name <email@example.com>"
                                    sender_email = sender.split('<')[1].split('>')[0].strip()
                                else:
                                    # Just use the whole sender field
                                    sender_email = sender.strip()
```

This section:
1. Extracts the sender's email address
2. Handles different sender formats (with or without display name)

```python
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
```

When a match is found:
1. Updates the tracking record to 'replied' status
2. Sets the replied_at timestamp
3. Returns the tracking ID
4. Commits the transaction
5. Logs the successful reply detection
6. Increments the reply counter

```python
            except Exception as e:
                current_app.logger.error(f"Error processing email {mail_id}: {str(e)}")
                # Continue to next email
        
        current_app.logger.info(f"Reply check complete. Found and processed {replies_found} new replies.")
```

Error handling:
1. Logs any errors processing a specific email
2. Continues to the next email (doesn't abort the whole process)
3. Logs a summary of replies found when complete

```python
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
```

Outer exception handling:
1. Logs any general errors in the reply checking process
2. Rolls back any open transactions
3. Always closes the IMAP connection and logs out
4. Always closes the database connection

## Safe Wrapper for Check Replies

```python
def safe_check_for_replies():
    """Safely run the reply check with error handling for the scheduler"""
    try:
        check_for_replies()
    except Exception as e:
        current_app.logger.error(f"Error in scheduled reply check: {str(e)}")
```

The `safe_check_for_replies` function:
1. Provides an extra layer of error handling for the scheduler
2. Prevents the scheduler from crashing if an error occurs
3. Logs any errors in the scheduled task
4. This is the function that's actually registered with the scheduler