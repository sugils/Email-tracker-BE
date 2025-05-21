# Email Campaign Management API - Complete Documentation

## Introduction

The Email Campaign Management API is a comprehensive backend system for managing email marketing campaigns. It allows users to create campaigns, manage recipient lists, design email templates, send emails, and track engagement metrics like opens, clicks, and replies.

## System Architecture

The system follows a modular architecture with clear separation of concerns:

1. **Route Layer (`app.py`)**: Handles HTTP requests, authentication, and routes to controllers
2. **Controller Layer (`controller.py`)**: Processes business logic, validates inputs, and formats responses
3. **Model Layer (`models.py`)**: Manages database operations and data access
4. **Helper Layer (`helper.py`)**: Provides utility functions, email sending, and tracking features

## Installation

### Requirements

Install the required packages using pip:

```bash
pip install -r requirements.txt
```

### Environment Variables

The application uses the following environment variables:

```
# Database Configuration
DB_HOST=localhost
DB_PORT=5432
DB_NAME=email_app
DB_USER=postgres
DB_PASS=your_password

# Email Configuration
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_app_password

# Application Configuration
BASE_URL=http://localhost:5000/
JWT_SECRET_KEY=your_secret_key
```

### Database Setup

The application will create the required database tables automatically on startup. Make sure you have a PostgreSQL database created with the name specified in your environment variables.

## API Endpoints

### Authentication

#### Register a New User

```
POST /api/register
```

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "secure_password",
  "full_name": "John Doe"
}
```

**Response:**
```json
{
  "message": "User registered successfully",
  "access_token": "jwt_token_here",
  "user": {
    "user_id": "uuid_here",
    "email": "user@example.com",
    "full_name": "John Doe"
  }
}
```

#### Login

```
POST /api/login
```

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "secure_password"
}
```

**Response:**
```json
{
  "message": "Login successful",
  "access_token": "jwt_token_here",
  "user": {
    "user_id": "uuid_here",
    "email": "user@example.com",
    "full_name": "John Doe"
  }
}
```

### Campaigns

#### Get All Campaigns

```
GET /api/campaigns
```

**Headers:**
```
Authorization: Bearer jwt_token_here
```

**Response:**
```json
[
  {
    "campaign_id": "uuid_here",
    "user_id": "uuid_here",
    "campaign_name": "Welcome Campaign",
    "subject_line": "Welcome to Our Service",
    "from_name": "My Company",
    "from_email": "info@mycompany.com",
    "reply_to_email": "support@mycompany.com",
    "created_at": "2023-05-20T15:30:00Z",
    "scheduled_at": null,
    "sent_at": "2023-05-21T10:00:00Z",
    "status": "completed",
    "is_active": true,
    "recipient_count": 150,
    "stats": {
      "sent_count": 150,
      "opened_count": 75,
      "clicked_count": 30,
      "replied_count": 5,
      "open_rate": 50.0,
      "click_rate": 20.0,
      "reply_rate": 3.33
    }
  }
]
```

#### Create a Campaign

```
POST /api/campaigns
```

**Headers:**
```
Authorization: Bearer jwt_token_here
```

**Request Body:**
```json
{
  "campaign_name": "Welcome Campaign",
  "subject_line": "Welcome to Our Service",
  "from_name": "My Company",
  "from_email": "info@mycompany.com",
  "reply_to_email": "support@mycompany.com",
  "template": {
    "name": "Welcome Template",
    "html_content": "<html><body>Hello {{first_name}}, welcome to our service!</body></html>",
    "text_content": "Hello {{first_name}}, welcome to our service!"
  },
  "recipients": ["uuid1", "uuid2", "uuid3"]
}
```

**Response:**
```json
{
  "message": "Campaign created successfully",
  "campaign_id": "uuid_here"
}
```

#### Get Campaign by ID

```
GET /api/campaigns/:campaign_id
```

**Headers:**
```
Authorization: Bearer jwt_token_here
```

**Response:**
```json
{
  "campaign_id": "uuid_here",
  "campaign_name": "Welcome Campaign",
  "subject_line": "Welcome to Our Service",
  "from_name": "My Company",
  "from_email": "info@mycompany.com",
  "reply_to_email": "support@mycompany.com",
  "created_at": "2023-05-20T15:30:00Z",
  "scheduled_at": null,
  "sent_at": "2023-05-21T10:00:00Z",
  "status": "completed",
  "is_active": true,
  "template": {
    "template_id": "uuid_here",
    "template_name": "Welcome Template",
    "html_content": "<html><body>Hello {{first_name}}, welcome to our service!</body></html>",
    "text_content": "Hello {{first_name}}, welcome to our service!"
  },
  "recipients": [
    {
      "recipient_id": "uuid_here",
      "email": "john@example.com",
      "first_name": "John",
      "last_name": "Doe"
    }
  ],
  "tracking_stats": {
    "overall": {
      "sent_count": 150,
      "opened_count": 75,
      "clicked_count": 30,
      "replied_count": 5,
      "open_rate": 50.0,
      "click_rate": 20.0,
      "reply_rate": 3.33
    },
    "recipients": [
      {
        "tracking_id": "uuid_here",
        "recipient_id": "uuid_here",
        "email": "john@example.com",
        "email_status": "opened",
        "sent_at": "2023-05-21T10:00:00Z",
        "opened_at": "2023-05-21T10:15:00Z",
        "clicked_at": null,
        "replied_at": null
      }
    ]
  }
}
```

#### Send Campaign

```
POST /api/campaigns/:campaign_id/send
```

**Headers:**
```
Authorization: Bearer jwt_token_here
```

**Request Body:**
```json
{
  "test_mode": false
}
```

**Response:**
```json
{
  "message": "Campaign sending in progress"
}
```

### Recipients

#### Get All Recipients

```
GET /api/recipients
```

**Headers:**
```
Authorization: Bearer jwt_token_here
```

**Response:**
```json
[
  {
    "recipient_id": "uuid_here",
    "user_id": "uuid_here",
    "email": "john@example.com",
    "first_name": "John",
    "last_name": "Doe",
    "company": "ACME Inc.",
    "position": "Marketing Manager",
    "custom_fields": {
      "subscription_level": "premium",
      "signed_up_date": "2023-01-15"
    },
    "created_at": "2023-05-15T10:00:00Z",
    "updated_at": "2023-05-15T10:00:00Z",
    "is_active": true
  }
]
```

#### Create a Recipient

```
POST /api/recipients
```

**Headers:**
```
Authorization: Bearer jwt_token_here
```

**Request Body:**
```json
{
  "email": "john@example.com",
  "first_name": "John",
  "last_name": "Doe",
  "company": "ACME Inc.",
  "position": "Marketing Manager",
  "custom_fields": {
    "subscription_level": "premium",
    "signed_up_date": "2023-01-15"
  }
}
```

**Response:**
```json
{
  "message": "Recipient created successfully",
  "recipient_id": "uuid_here"
}
```

#### Create Multiple Recipients (Bulk)

```
POST /api/recipients/bulk
```

**Headers:**
```
Authorization: Bearer jwt_token_here
```

**Request Body:**
```json
{
  "recipients": [
    {
      "email": "john@example.com",
      "first_name": "John",
      "last_name": "Doe"
    },
    {
      "email": "jane@example.com",
      "first_name": "Jane",
      "last_name": "Smith"
    }
  ]
}
```

**Response:**
```json
{
  "message": "Created 2 recipients, skipped 0 duplicates",
  "created_count": 2,
  "skipped_count": 0
}
```

#### Get Recipient by ID

```
GET /api/recipients/:recipient_id
```

**Headers:**
```
Authorization: Bearer jwt_token_here
```

**Response:**
```json
{
  "recipient_id": "uuid_here",
  "user_id": "uuid_here",
  "email": "john@example.com",
  "first_name": "John",
  "last_name": "Doe",
  "company": "ACME Inc.",
  "position": "Marketing Manager",
  "custom_fields": {
    "subscription_level": "premium",
    "signed_up_date": "2023-01-15"
  },
  "created_at": "2023-05-15T10:00:00Z",
  "updated_at": "2023-05-15T10:00:00Z",
  "is_active": true
}
```

#### Update Recipient

```
PUT /api/recipients/:recipient_id
```

**Headers:**
```
Authorization: Bearer jwt_token_here
```

**Request Body:**
```json
{
  "email": "john.doe@example.com",
  "first_name": "John",
  "last_name": "Doe",
  "company": "ACME Corporation",
  "position": "Senior Marketing Manager",
  "custom_fields": {
    "subscription_level": "enterprise",
    "signed_up_date": "2023-01-15"
  }
}
```

**Response:**
```json
{
  "message": "Recipient updated successfully",
  "recipient_id": "uuid_here"
}
```

#### Delete Recipient

```
DELETE /api/recipients/:recipient_id
```

**Headers:**
```
Authorization: Bearer jwt_token_here
```

**Response:**
```json
{
  "message": "Recipient deleted successfully",
  "recipient_id": "uuid_here"
}
```

#### Delete Multiple Recipients (Bulk)

```
POST /api/recipients/bulk-delete
```

**Headers:**
```
Authorization: Bearer jwt_token_here
```

**Request Body:**
```json
{
  "recipient_ids": ["uuid1", "uuid2", "uuid3"]
}
```

**Response:**
```json
{
  "message": "Successfully deleted 3 recipients",
  "deleted_count": 3,
  "recipient_ids": ["uuid1", "uuid2", "uuid3"]
}
```

### Templates

#### Get All Templates

```
GET /api/templates
```

**Headers:**
```
Authorization: Bearer jwt_token_here
```

**Response:**
```json
[
  {
    "template_id": "uuid_here",
    "user_id": "uuid_here",
    "campaign_id": "uuid_here",
    "template_name": "Welcome Template",
    "html_content": "<html><body>Hello {{first_name}}, welcome to our service!</body></html>",
    "text_content": "Hello {{first_name}}, welcome to our service!",
    "created_at": "2023-05-15T10:00:00Z",
    "updated_at": "2023-05-15T10:00:00Z",
    "is_active": true
  }
]
```

### Dashboard

#### Get Dashboard Data

```
GET /api/dashboard
```

**Headers:**
```
Authorization: Bearer jwt_token_here
```

**Response:**
```json
{
  "counts": {
    "campaigns": 5,
    "recipients": 500,
    "templates": 3,
    "emails_sent": 1500
  },
  "overall_stats": {
    "total_sent": 1500,
    "total_opened": 750,
    "total_clicked": 300,
    "total_replied": 75,
    "open_rate": 50.0,
    "click_rate": 20.0,
    "reply_rate": 5.0
  },
  "campaign_stats": [
    {
      "campaign_id": "uuid_here",
      "campaign_name": "Welcome Campaign",
      "sent_count": 150,
      "opened_count": 75,
      "clicked_count": 30,
      "replied_count": 5,
      "open_rate": 50.0,
      "click_rate": 20.0,
      "reply_rate": 3.33
    }
  ],
  "recent_campaigns": [
    {
      "campaign_id": "uuid_here",
      "campaign_name": "Welcome Campaign",
      "subject_line": "Welcome to Our Service",
      "status": "completed",
      "created_at": "2023-05-20T15:30:00Z"
    }
  ],
  "recent_recipients": [
    {
      "recipient_id": "uuid_here",
      "email": "john@example.com",
      "first_name": "John",
      "last_name": "Doe",
      "created_at": "2023-05-15T10:00:00Z"
    }
  ]
}
```

### Tracking

#### Mark Email as Replied

```
POST /api/campaigns/:campaign_id/mark-replied
```

**Headers:**
```
Authorization: Bearer jwt_token_here
```

**Request Body:**
```json
{
  "recipient_id": "uuid_here"
}
```

**Response:**
```json
{
  "message": "Email marked as replied successfully",
  "tracking_id": "uuid_here",
  "replied_at": "2023-05-21T14:30:00Z"
}
```

### Utility Endpoints

#### Authentication Test

```
GET /api/auth-test
```

**Headers:**
```
Authorization: Bearer jwt_token_here
```

**Response:**
```json
{
  "status": "success",
  "message": "Authentication successful",
  "user_id": "uuid_here",
  "timestamp": "2023-05-21T15:30:00Z"
}
```

#### Health Check

```
GET /api/health-check
```

**Response:**
```json
{
  "status": "success",
  "message": "API is online",
  "timestamp": "2023-05-21T15:30:00Z"
}
```

## Tracking Features

### Email Open Tracking

The system uses a 1x1 transparent pixel image to track email opens. When a recipient opens an email, their email client loads the tracking pixel, triggering a request to:

```
GET /track/open/:tracking_pixel_id
```

This endpoint records the open event in the database and returns a transparent GIF image.

### Link Click Tracking

All links in the email are rewritten to point to the tracking endpoint:

```
GET /track/click/:tracking_id/:url_tracking_id
```

This endpoint records the click event and redirects the user to the original URL.

### JavaScript Beacon Tracking

As a backup for email clients that block images, the system adds a JavaScript beacon:

```
GET /track/beacon/:tracking_pixel_id
```

This endpoint records an open event similar to the tracking pixel.

### Reply Detection

The system periodically checks the configured email inbox for replies to campaign emails. It identifies replies by the "Re:" prefix in the subject line and matches them to the original campaign.

## Database Schema

### users
- user_id (UUID, Primary Key)
- email (VARCHAR, Unique)
- password_hash (VARCHAR)
- full_name (VARCHAR)
- created_at (TIMESTAMP)
- updated_at (TIMESTAMP)
- is_active (BOOLEAN)

### email_campaigns
- campaign_id (UUID, Primary Key)
- user_id (UUID, Foreign Key)
- campaign_name (VARCHAR)
- subject_line (VARCHAR)
- from_name (VARCHAR)
- from_email (VARCHAR)
- reply_to_email (VARCHAR)
- created_at (TIMESTAMP)
- scheduled_at (TIMESTAMP)
- sent_at (TIMESTAMP)
- status (VARCHAR)
- is_active (BOOLEAN)

### email_templates
- template_id (UUID, Primary Key)
- user_id (UUID, Foreign Key)
- campaign_id (UUID, Foreign Key)
- template_name (VARCHAR)
- html_content (TEXT)
- text_content (TEXT)
- created_at (TIMESTAMP)
- updated_at (TIMESTAMP)
- is_active (BOOLEAN)

### recipients
- recipient_id (UUID, Primary Key)
- user_id (UUID, Foreign Key)
- email (VARCHAR)
- first_name (VARCHAR)
- last_name (VARCHAR)
- company (VARCHAR)
- position (VARCHAR)
- custom_fields (JSONB)
- created_at (TIMESTAMP)
- updated_at (TIMESTAMP)
- is_active (BOOLEAN)

### campaign_recipients
- campaign_recipient_id (UUID, Primary Key)
- campaign_id (UUID, Foreign Key)
- recipient_id (UUID, Foreign Key)
- created_at (TIMESTAMP)
- is_active (BOOLEAN)

### email_tracking
- tracking_id (UUID, Primary Key)
- campaign_id (UUID, Foreign Key)
- recipient_id (UUID, Foreign Key)
- email_status (VARCHAR)
- sent_at (TIMESTAMP)
- delivered_at (TIMESTAMP)
- opened_at (TIMESTAMP)
- clicked_at (TIMESTAMP)
- replied_at (TIMESTAMP)
- bounced_at (TIMESTAMP)
- tracking_pixel_id (VARCHAR, Unique)
- open_count (INTEGER)
- click_count (INTEGER)
- created_at (TIMESTAMP)
- updated_at (TIMESTAMP)
- is_active (BOOLEAN)

### url_tracking
- url_tracking_id (UUID, Primary Key)
- tracking_id (UUID, Foreign Key)
- original_url (TEXT)
- tracking_url (TEXT)
- click_count (INTEGER)
- first_clicked_at (TIMESTAMP)
- last_clicked_at (TIMESTAMP)
- created_at (TIMESTAMP)
- is_active (BOOLEAN)

## Conclusion

This API provides a comprehensive solution for email campaign management with robust tracking capabilities. The modular architecture makes it easy to maintain and extend, while the tracking features provide valuable insights into email engagement.