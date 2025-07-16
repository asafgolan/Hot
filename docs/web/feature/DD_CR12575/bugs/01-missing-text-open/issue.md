# Missing Text in Upgrade Flow - OPEN

**Bug ID**: 01
**Status**: OPEN
**Design Ticket**: DT_6.1.4.1

## Environment
- **Base URL**: https://selfservicetest.hot.net.il
- **Browser**: Desktop Macbook Pro 14 inch (macOS 14.5) Chrome
- **User**: Asaf Golan
- **Date Reported**: 2025-07-16
- **Customer**: Asaf Golan (valid fiber service subscriber with no valid login session)

## Steps to Reproduce:
1. With user Asaf Golan (no valid login session), navigate to `/upgrade-fiber`
2. User is redirected to login page with ref in the URL: `/login?PageName=upgrade-fiber%2Fwelcome`
3. User enters correct OTP credentials (ID and phone number) and clicks submit
4. User is redirected to welcome page with URL: `/upgrade-fiber/welcome`
5. User clicks continue button


## Actual Result:

![Missing text in steps section](./assets/invalid_welcome_view_DT_6.1.4.1.png)
*Screenshot shows steps section with missing explanatory text*

## Expected Result:

![Expected complete steps section](./assets/valid_welcome_view_DT_6.1.4.1.png)
*Screenshot shows how steps section should appear with all text visible*

## Technical Details
- **Element ID**: `#steps-container`
- **Expected Text Elements**: All step description texts should be visible
- **Related Component**: Step progress indicator in upgrade flow
- **Design Ticket**: DT_6.1.4.1
- **Severity**: Medium - Functional but confusing UX

## Possible Causes
- Hebrew text direction (RTL) styling issue
- Missing text in content management system
- Responsive design breakpoints not properly handling mobile viewport

## Assigned To
Frontend team
