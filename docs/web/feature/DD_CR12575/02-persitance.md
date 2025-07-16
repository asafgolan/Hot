# Persistence and Session Management

## Session Tracking

### Client Session Management

1. Client sessions are tracked in the EAI reporting data system with the following parameters:
   - Session ID: Generated upon initial page load
   - Client ID: Retrieved from authentication service
   - Entry Point: Which SMS campaign or entry URL was used
   - Current Step: Current step in the upgrade flow
   - Timestamp: When the session was created/updated

### Test Session Manipulation

1. **Checking Feature Availability**:
   ```python
   # E2E test to verify feature is enabled in the environment
   async def test_feature_availability(page):
       # Navigate to the feature URL
       await page.goto('https://selfservicetest.hot.net.il/upgrade-fiber')
       
       # Check if redirected to login (expected when no session)
       assert 'login' in page.url
       
       # After login, check for welcome page elements
       # ... login steps ...
       await page.wait_for_selector('#welcome-page')
   ```

2. **Testing Different Customer States**:
   ```python
   # Helper function to set customer state for testing
   async def set_customer_state(customer_type):
       # API call to test environment to modify customer state
       # This would typically be a backend API call, not frontend
       ...
   ```

3. **Session Reset for Testing**:
   - Clear cookies and local storage between tests
   - Programmatically reset the user state via backend API
   - Force new session creation via API before each test

## Data Persistence Points

1. Customer verification data is stored in `UpgradeProcess` table
2. Selected bandwidth package is stored in `CustomerSelection` table
3. Scheduled installation details are stored in `InstallationAppointment` table

## API Response Caching

1. Customer details API responses are cached for 15 minutes
2. Available time slots are cached for 2 minutes
3. Cache invalidation occurs when an appointment is successfully scheduled
