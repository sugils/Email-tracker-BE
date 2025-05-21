# Email Campaign Management API - Code Structure Summary

I've restructured the codebase into a more organized and maintainable structure following the requested file organization:

## 1. File Structure

### `app.py`
- Main application file that initializes the Flask app, defines routes, and handles HTTP requests
- Routes are defined here and they call the appropriate controller functions
- Includes error handlers, middleware for logging, and app configuration
- JWT authentication setup and connection to the scheduler

### `controller.py`
- Contains business logic for processing requests
- Implements input validation
- Calls models to perform database operations
- Formats response data for the API
- Organized into controller classes for different API resources

### `models.py`
- Handles all database operations
- Defines SQL queries and executes them
- Provides methods to create, read, update and delete data from the database
- Organized into model classes for different database tables

### `helper.py`
- Contains utility functions used across the application
- Database connection management
- Transaction handling
- Email sending functions
- Link rewriting for tracking
- Reply checking functionality

## 2. API Endpoints Overview

### Authentication Endpoints
- `/api/register` (POST): Register a new user
- `/api/login` (POST): Login and get JWT token

### Campaign Endpoints
- `/api/campaigns` (GET): Get all campaigns for the current user
- `/api/campaigns` (POST): Create a new campaign
- `/api/campaigns/<campaign_id>` (GET): Get a specific campaign
- `/api/campaigns/<campaign_id>/send` (POST): Send a campaign or test email
- `/api/dashboard` (GET): Get dashboard overview with campaign stats

### Recipient Endpoints
- `/api/recipients` (GET): Get all recipients for the current user
- `/api/recipients` (POST): Create a new recipient
- `/api/recipients/bulk` (POST): Create multiple recipients at once
- `/api/recipients/<recipient_id>` (GET): Get a specific recipient
- `/api/recipients/<recipient_id>` (PUT): Update a recipient
- `/api/recipients/<recipient_id>` (DELETE): Delete a recipient
- `/api/recipients/bulk-delete` (POST): Delete multiple recipients

### Template Endpoints
- `/api/templates` (GET): Get all templates for the current user

### Tracking Endpoints
- `/track/open/<tracking_pixel_id>` (GET): Track email opens via tracking pixel
- `/track/click/<tracking_id>/<url_tracking_id>` (GET): Track email link clicks
- `/track/beacon/<tracking_pixel_id>` (GET): JavaScript-based tracking as backup
- `/api/campaigns/<campaign_id>/mark-replied` (POST): Manually mark an email as replied

### Utility and Debug Endpoints
- `/api/auth-test` (GET): Test endpoint that requires authentication
- `/api/health-check` (GET): Health check endpoint
- `/api/debug/tracking/<campaign_id>` (GET): Debug endpoint for tracking data
- `/api/debug/check-replies` (GET): Manually trigger reply check
- `/api/debug/track-open/<campaign_id>/<recipient_id>` (GET): Manually trigger open event
- `/api/debug/test-click/<tracking_id>` (GET): Generate a test click for debugging

## 3. Key Features

### Email Campaign Management
- Create and manage email campaigns
- Design email templates with personalization
- Manage recipient lists
- Schedule and send campaigns

### Email Tracking
- Track email opens using tracking pixels
- Track link clicks in emails
- Monitor and analyze campaign performance

### Reply Detection
- Automatically check for replies to campaign emails
- Mark emails as replied in the system

### Dashboard Analytics
- View campaign statistics
- Track open rates, click rates, and reply rates
- Monitor overall email campaign performance

## 4. Database Structure

The application uses PostgreSQL with the following tables:
1. `users` - Store user accounts
2. `email_campaigns` - Store campaign information
3. `email_templates` - Store email templates
4. `recipients` - Store recipient information
5. `campaign_recipients` - Link campaigns to recipients (many-to-many)
6. `email_tracking` - Track email engagement metrics
7. `url_tracking` - Track link clicks in emails

## 5. Authentication

The API uses JWT (JSON Web Tokens) for authentication. After successful login, users receive a token that must be included in the Authorization header for subsequent requests.

## 6. Background Tasks

The application uses background tasks for:
- Sending emails asynchronously
- Checking for replies periodically using a scheduler

This architecture follows a clean separation of concerns, making the code more maintainable, testable, and scalable.