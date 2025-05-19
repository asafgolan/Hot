import pytest
from playwright.sync_api import Playwright, Page, expect
from time import sleep

# We're using the TestJourney class approach from the test file, not decorators
# from ...utils.metrics import TestJourney


@pytest.fixture(scope="function")
def page(playwright: Playwright):
    # Using iPhone 13 device descriptor for consistent mobile testing
    iphone_13 = playwright.devices['iPhone 13']
    browser = playwright.webkit.launch(headless=True)
    context = browser.new_context(**iphone_13)
    page = context.new_page()
    
    # Return the page for testing
    yield page
    
    # Clean up after test
    context.close()
    browser.close()

# Step 1: Navigate to HOT website and open mobile menu
def navigate_to_hot_website(page: Page):
    """Navigate to the HOT website and open the mobile menu"""
    
    page.goto("https://www.hot.net.il/heb/main/")
    page.get_by_role("link", name="לחץ לפתוח תפריט מובייל").click()
    
# Step 2: Navigate to the login page
def navigate_to_login_page(page: Page):
    """Navigate from mobile menu to the login page"""
    page.get_by_role("menuitem", name="אזור אישי").click()
    page.locator("#headerMenu_m_00").get_by_role("listitem").filter(
        has_text="התחברות לאזור האישי").click()
    
# Step 3: Enter credentials and request SMS
def enter_credentials_and_request_sms(page: Page, id_number: str, phone_number: str):
    """Fill in login form and request SMS verification code"""
    # Enter ID and phone number
    page.get_by_role("textbox", name="תעודת זהות").click()
    page.get_by_role("textbox", name="תעודת זהות").fill(id_number)
    page.get_by_role("textbox", name="טלפון נייד").click()
    page.get_by_role("textbox", name="טלפון נייד").fill(phone_number)
    
    # Wait for form to be fully interactive
    sleep(2)
    
    # Request OTP SMS with reliable selector
    page.locator("div.pageSubmit > button[type='submit']").click(force=True, timeout=5000)
    
    # Wait for SMS to be processed
    sleep(5)

# Step 4: Enter OTP code
def enter_otp_code(page: Page, otp_code: str):
    """Enter the OTP code into the verification form"""
    # Click on the OTP input field instruction text
    page.get_by_text("הזינו כאן את הקוד וסיימנו").click()
    
    # Enter the OTP code
    page.get_by_label("", exact=True).click()
    page.get_by_label("", exact=True).fill(otp_code)

# Step 5: Submit login form with OTP
def submit_otp_login(page: Page):
    """Click the login button to submit the OTP form"""
    page.get_by_role("button", name="כניסה לחשבון", exact=True).click()
    sleep(2)  # Wait for response