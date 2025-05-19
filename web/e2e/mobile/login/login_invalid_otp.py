from .pom import *
from ...utils.metrics import TestMetrics

# Test function using the modular steps with metrics
def test_hot_mobile_login_invalid_otp(page):
    # Create metrics collector with unique UUID
    metrics = TestMetrics(test_name="hot_mobile_login_invalid_otp")
    # Step 1: Navigate to HOT website with metrics
    metrics.start_step("navigate_to_hot_website")
    try:
        navigate_to_hot_website(page)
        metrics.end_step("navigate_to_hot_website", status="success")
    except Exception as e:
        metrics.end_step("navigate_to_hot_website", status="failure", data={"error": str(e)})
        raise
    
    # Step 2: Navigate to login page with metrics
    metrics.start_step("navigate_to_login_page")
    try:
        navigate_to_login_page(page)
        metrics.end_step("navigate_to_login_page", status="success")
    except Exception as e:
        metrics.end_step("navigate_to_login_page", status="failure", data={"error": str(e)})
        raise
    
    # Step 3: Fill credentials and request SMS with metrics
    metrics.start_step("enter_credentials")
    try:
        enter_credentials_and_request_sms(page, "301196085", "0528214946")
        metrics.end_step("enter_credentials", status="success", 
                       data={"id_used": "301196xxx", "phone": "052821xxxx"})
    except Exception as e:
        metrics.end_step("enter_credentials", status="failure", data={"error": str(e)})
        raise
    
    # Step 4: Enter invalid OTP with metrics
    metrics.start_step("enter_otp")
    try:
        enter_otp_code(page, "123123")
        metrics.end_step("enter_otp", status="success", data={"otp": "123123"})
    except Exception as e:
        metrics.end_step("enter_otp", status="failure", data={"error": str(e)})
        raise
    
    # Step 5: Submit login and check for error with metrics
    metrics.start_step("submit_login")
    try:
        submit_otp_login(page)
        metrics.end_step("submit_login", status="success")
    except Exception as e:
        metrics.end_step("submit_login", status="failure", data={"error": str(e)})
        raise
    
    # Verify error message is displayed with metrics
    metrics.start_step("verify_error_message")
    try:
        # Approach 1: Use a CSS selector targeting the stable class name
        error_message = page.locator("div.errorComment")
        expect(error_message).to_be_visible()
        
        # Approach 2: Use partial text matching which is more resilient
        expect(page.get_by_text("יש להכניס את הקוד", exact=False)).to_be_visible()
        
        # Record success with the actual error text
        error_text = error_message.inner_text()
        metrics.end_step("verify_error_message", status="success", 
                      data={"error_text": error_text})
    except Exception as e:
        metrics.end_step("verify_error_message", status="failure", data={"error": str(e)})
        raise
    
    # Complete the test metrics and record overall results
    metrics.finish()