# models.py - Detailed Documentation

## Overview

`models.py` handles all database operations for the Email Campaign Management API. It defines the structure of database tables and provides methods to interact with the data. Each model class corresponds to a database table or related group of tables.

## Imports

```python
from flask import current_app, g
import json
import uuid
import base64
from datetime import datetime
import psycopg2
import psycopg2.extras
from helper import get_db_connection, get_direct_db_connection
```

- **current_app**: Access to the Flask application context for logging
- **g**: Flask application context for request-scoped resources
- **json**: JSON serialization for custom fields
- **uuid**: Generate UUIDs for tracking IDs
- **base64**: Encode/decode the tracking pixel GIF image
- **datetime**: Date and time operations
- **psycopg2**: PostgreSQL database adapter
- **get_db_connection/get_direct_db_connection**: Helper functions for database connections

## Database Initialization

```python
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
```

The `init_db` function:
1. Gets a database connection and cursor
2. Executes SQL statements to create database tables if they don't exist
3. Each `CREATE TABLE IF NOT EXISTS` statement defines a table schema with columns and constraints

The database schema includes:
- **users**: Store user accounts and credentials
- **email_campaigns**: Campaign details and status
- **email_templates**: HTML and text content for emails
- **recipients**: Contact information for email recipients
- **campaign_recipients**: Many-to-many relationship between campaigns and recipients
- **email_tracking**: Track email opens, clicks, and replies
- **url_tracking**: Track specific link clicks within emails

```python
    conn.commit()
    current_app.logger.info("Database tables initialized")
```

Commits the changes and logs that initialization is complete.

## UserModel

```python
class UserModel:
    def find_by_email(self, email):
        """Find a user by email address"""
        conn, cur = get_db_connection()
        cur.execute("SELECT * FROM users WHERE email = %s", (email,))
        return cur.fetchone()
```

The `find_by_email` method:
1. Gets a database connection and cursor
2. Executes a parameterized SQL query to find a user by email
3. Returns the user record or None

```python
    def create(self, email, password_hash, full_name):
        """Create a new user"""
        conn, cur = get_db_connection()
        cur.execute("""
            INSERT INTO users (email, password_hash, full_name)
            VALUES (%s, %s, %s)
            RETURNING user_id, email, full_name
        """, (email, password_hash, full_name))
        
        return cur.fetchone()
```

The `create` method:
1. Inserts a new user record with email, hashed password, and name
2. Uses `RETURNING` to get the newly created record data
3. Returns the new user record with ID

## CampaignModel

```python
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
```

The `get_all_by_user` method:
1. Gets all active campaigns for a specific user
2. Orders by creation date (newest first)
3. Returns a list of campaign records

```python
    def count_recipients(self, campaign_id):
        """Count recipients for a campaign"""
        conn, cur = get_db_connection()
        cur.execute("""
            SELECT COUNT(*) as recipient_count FROM campaign_recipients
            WHERE campaign_id = %s AND is_active = TRUE
        """, (campaign_id,))
        return cur.fetchone()['recipient_count']
```

The `count_recipients` method:
1. Counts the number of active recipients for a campaign
2. Returns the count as an integer

```python
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
```

The `get_tracking_stats` method:
1. Uses PostgreSQL's `COUNT() FILTER (WHERE ...)` to count events by type
2. Counts sent, opened, clicked, and replied emails in a single query
3. Returns a record with all four counts

```python
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
```

The `create` method:
1. Inserts a new campaign record with the provided details
2. Returns the ID of the newly created campaign

## RecipientModel

```python
class RecipientModel:
    def find_by_email_excluding(self, user_id, email, recipient_id):
        """Find a recipient by email, excluding a specific recipient_id"""
        conn, cur = get_db_connection()
        cur.execute("""
            SELECT * FROM recipients
            WHERE user_id = %s AND email = %s AND recipient_id != %s AND is_active = TRUE
        """, (user_id, email, recipient_id))
        return cur.fetchone()
```

The `find_by_email_excluding` method:
1. Checks if a recipient with a given email exists (for a specific user)
2. Excludes a specific recipient ID from the search
3. Used when updating a recipient to check for duplicates
4. Returns the duplicate recipient record or None

```python
    def soft_delete(self, recipient_id):
        """Soft delete a recipient"""
        conn, cur = get_db_connection()
        cur.execute("""
            UPDATE recipients
            SET is_active = FALSE, updated_at = NOW()
            WHERE recipient_id = %s
        """, (recipient_id,))
```

The `soft_delete` method:
1. "Soft deletes" a recipient by setting `is_active = FALSE`
2. Updates the `updated_at` timestamp
3. This preserves the record for historical data while hiding it from active use

```python
    def remove_from_campaigns(self, recipient_id):
        """Remove a recipient from all campaigns"""
        conn, cur = get_db_connection()
        cur.execute("""
            UPDATE campaign_recipients
            SET is_active = FALSE
            WHERE recipient_id = %s
        """, (recipient_id,))
```

The `remove_from_campaigns` method:
1. "Soft removes" a recipient from all campaigns
2. Sets `is_active = FALSE` in the campaign_recipients join table
3. This preserves campaign history while removing the recipient from active campaigns

```python
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
```

The `validate_ownership` method:
1. Dynamically builds a SQL query to check multiple recipient IDs
2. Verifies that all recipients belong to the specified user
3. Returns a list of valid recipient IDs
4. Used for bulk operations to filter out invalid IDs

## TrackingModel

```python
class TrackingModel:
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
```

The `record_open` method:
1. Gets a direct database connection (not tied to Flask's request context)
2. Finds the tracking record associated with the pixel ID

```python
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
```

This section:
1. Logs that the tracking entry was found
2. Updates the tracking data with a sophisticated SQL query that:
   - Sets status to 'opened' only if current status is 'sending', 'sent', or 'pending'
   - Keeps higher status levels ('clicked' or 'replied') to avoid downgrading
   - Sets opened_at timestamp if it's NULL
   - Increments the open count
   - Updates the updated_at timestamp

```python
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
```

This section:
1. Commits the update transaction
2. Logs detailed information about the update
3. Performs a verification query to double-check the update (for debugging)

```python
            # Return a 1x1 transparent pixel
            pixel = base64.b64decode('R0lGODlhAQABAIAAAP///wAAACH5BAEAAAAALAAAAAABAAEAAAICRAEAOw==')
            
            return {'pixel': pixel}
```

Returns a 1x1 transparent GIF pixel as a binary object to be served to the email client.

```python
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
```

Error handling section:
1. Logs any errors that occur
2. Rolls back the transaction if needed
3. Returns a transparent pixel anyway (to avoid breaking email display)
4. Closes the database connection in a finally block

```python
    def get_fallback_pixel(self):
        """Get a transparent pixel for fallback return"""
        return base64.b64decode('R0lGODlhAQABAIAAAP///wAAACH5BAEAAAAALAAAAAABAAEAAAICRAEAOw==')
```

This utility method returns a transparent GIF pixel as a fallback.

```python
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
```

The `record_click` method:
1. Gets a direct database connection
2. Finds the URL tracking record for the specific link

```python
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
```

This sophisticated update query:
1. Sets status to 'clicked' unless it's already 'replied'
2. Ensures opened_at is set (clicking implies opening)
3. Sets open_count to at least 1
4. Sets clicked_at timestamp if it's NULL
5. Increments the click count
6. Updates the updated_at timestamp

## Model Instances

```python
# Initialize model instances
user_model = UserModel()
campaign_model = CampaignModel()
recipient_model = RecipientModel()
template_model = TemplateModel()
tracking_model = TrackingModel()
```

Creates instances of each model class to be imported and used by controllers.