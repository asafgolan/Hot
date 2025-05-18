from pom import *

# Test function using the modular steps
def test_hot_mobile_login_invalid_otp(page):
    # Step 1: Navigate to HOT website
    navigate_to_hot_website(page)
    
    # Step 2: Navigate to login page
    navigate_to_login_page(page)
    
    # Step 3: Fill credentials and request SMS
    enter_credentials_and_request_sms(page, "301196085", "0528214946")
    
    # Step 4: Enter invalid OTP
    enter_otp_code(page, "123123")
    
    # Step 5: Submit login and check for error
    submit_otp_login(page)
    
    # Verify error message is displayed for invalid OTP using multiple approaches
    
    # Approach 1: Use a CSS selector targeting the stable class name
    error_message = page.locator("div.errorComment")
    expect(error_message).to_be_visible()
    
    #Approach 2: Use partial text matching which is more resilient
    expect(page.get_by_text("יש להכניס את הקוד", exact=False)).to_be_visible()