import pytest

# No device-specific configuration in conftest.py as each test handles its own device emulation

# @pytest.fixture(scope="session")
# def browser_type_launch_args(browser_type_launch_args):
#     """Override browser launch arguments for all tests."""
#     return {
#         **browser_type_launch_args,
#         "headless": False,  # Set to True for CI/production runs
#     }
