from prefect import flow, task
import pytest
import sys
import os
from prefect.testing.utilities import prefect_test_harness
from prefect.tasks import NO_CACHE  # Import the NO_CACHE policy
import time

# Add the parent directory to sys.path to allow imports from misc
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

@pytest.fixture(autouse=True, scope="session")
def prefect_test_fixture():
    with prefect_test_harness():
        yield


@task
def init_tv():
    # Initialize TV connection from the misc directory
    from misc.tv_app_navigation import init_tv
    return init_tv()
    
@task(cache_policy=NO_CACHE)  # Disable caching for this task since TV object can't be serialized
def navigate_to_hot_app_samsung_43_crystal(tv):
    from misc.tv_app_navigation import navigate_and_select_app
    return navigate_and_select_app(tv)

@task(cache_policy=NO_CACHE)
def insert_otp_user(tv):
    user = "816178339"
    phone = "0523244358"
    otp = "123456"
    # Insert user on a phone like keyboard with remote control when default  button is on 0
    

    # click 0
    tv.send_key("KEY_ENTER")

    # click 5
    tv.send_key("KEY_UP")
    tv.send_key("KEY_UP")
    tv.send_key("KEY_ENTER")

    # click 2
    tv.send_key("KEY_UP")
    tv.send_key("KEY_ENTER")

    # click 3
    tv.send_key("KEY_RIGHT")
    tv.send_key("KEY_ENTER")

    # click 2
    tv.send_key("KEY_LEFT")
    tv.send_key("KEY_ENTER")

    # click 4 * 2
    tv.send_key("KEY_LEFT")
    tv.send_key("KEY_DOWN")
    tv.send_key("KEY_ENTER")
    time.sleep(1)
    tv.send_key("KEY_ENTER")
    time.sleep(1)

    # click 3
    tv.send_key("KEY_RIGHT")
    tv.send_key("KEY_RIGHT")
    tv.send_key("KEY_UP")
    tv.send_key("KEY_ENTER")
    time.sleep(1)

    # click 5
    tv.send_key("KEY_LEFT")
    tv.send_key("KEY_DOWN")
    tv.send_key("KEY_ENTER")
    time.sleep(1)
    
    
    # click 8
    tv.send_key("KEY_DOWN")
    tv.send_key("KEY_ENTER")
    time.sleep(1)

    # submit otp form
    tv.send_key("KEY_ENTER")
    time.sleep(5)

    #click 1
    tv.send_key("KEY_UP")
    tv.send_key("KEY_UP")
    tv.send_key("KEY_UP")
    tv.send_key("KEY_LEFT")
    tv.send_key("KEY_ENTER")
    time.sleep(1)
    
    #click 2
    tv.send_key("KEY_RIGHT")
    tv.send_key("KEY_ENTER")
    time.sleep(1)

    #click 3
    tv.send_key("KEY_RIGHT")
    tv.send_key("KEY_ENTER")
    time.sleep(1)

    #click 4
    tv.send_key("KEY_LEFT")
    tv.send_key("KEY_LEFT")
    tv.send_key("KEY_DOWN")
    tv.send_key("KEY_ENTER")
    time.sleep(1)

    #click 5
    tv.send_key("KEY_RIGHT")
    tv.send_key("KEY_ENTER")
    time.sleep(1)

    #click 6
    tv.send_key("KEY_RIGHT")
    tv.send_key("KEY_ENTER")
    time.sleep(1)

    #submit otp code
    tv.send_key("KEY_ENTER")
    time.sleep(5)
    
    
    
    
    

    
    
    

    # submit form with התחבר button
    
    time.sleep(2)


    
    return True
    

@flow
def otp_flow():
    # Initialize TV and get the connection object
    tv = init_tv()
    
    # Pass the TV connection to navigate function
    navigate_to_hot_app_samsung_43_crystal(tv)
    
    # Enter OTP
    insert_otp_user(tv)
    
    return True

def test_otp_flow():
    assert otp_flow() == True

if __name__ == "__main__":
    # Run the flow directly when the script is executed
    print("Running OTP TV authentication flow...")
    result = otp_flow()
    print(f"Flow completed with result: {result}")