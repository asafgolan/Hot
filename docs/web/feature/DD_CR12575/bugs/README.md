# Cable to Fiber Upgrade Flow - Bug Tracking

This section contains all reported bugs for the Cable to Fiber Upgrade Flow (DD_CR12575) feature.

## Bug Status Categories

- **OPEN**: Bug has been reported but not yet addressed
- **IN-PROGRESS**: Bug is currently being fixed
- **PENDING-VERIFICATION**: Fix has been implemented but awaits testing verification
- **CLOSED**: Bug has been resolved and verified

## Current Bugs

<details>
<summary><strong>01-missing-text-open</strong>: Missing Text in Upgrade Flow (DT_6.1.4.1) - OPEN</summary>

- **Reported**: 2025-07-16
- **Severity**: Medium
- **Component**: Step progress indicator
- **Details**: [Full bug report](./01-missing-text-open/01-missing-text.md)
- **Screenshots**: [Expected](./01-missing-text-open/assets/valid_welcome_view_DT_6.1.4.1.png) | [Actual](./01-missing-text-open/assets/invalid_welcome_view_DT_6.1.4.1.png)

</details>

<details>
<summary><strong>02-logged-in-user-invalid-99-success-msg-OPEN</strong>: Fiber User Receives Incorrect Success Code 99 - OPEN</summary>

- **Reported**: 2025-07-16
- **Severity**: High
- **Component**: User eligibility validation
- **Details**: [Full bug report](./02-logged-in-user-invalid-99-success-msg-OPEN/issue.md)
- **Screenshots**: [Expected](./02-logged-in-user-invalid-99-success-msg-OPEN/assets/valid_welcome_view_expected.png) | [Actual](./02-logged-in-user-invalid-99-success-msg-OPEN/assets/invalid_success_msg_actual.png)

</details>

<!-- Add new bugs here following the same pattern -->

## Bug Reporting Guidelines

1. Create a new folder following the pattern: `[bug-number]-[brief-name]-[status]`
2. Place all assets (screenshots, videos) in an `assets` subfolder
3. Use the standard bug report template
4. Update this index when adding new bugs
5. When a bug status changes, rename the folder to reflect the new status
