# Cable to Fiber Upgrade Flow: Step by Step

## One-Click Fiber Upgrade Process

```mermaid
graph TD
    %% Initial SMS and Landing Flow
    Start[Customer Receives SMS] -->|SMS contains personalized URL| Click[Customer clicks URL]
    Click --> SessionCheck{Is Session Valid?}
    SessionCheck -->|No| TimeoutView[Session Timeout View]
    SessionCheck -->|Yes| ProcessEntry[Process Entry in Personal Zone]
    
    %% Entry to Process
    ProcessEntry --> DBRecord[Create Process Record in Database]
    DBRecord --> EligibilityCheck[Core System Eligibility Check]
    
    %% Customer Type and Eligibility Checks
    EligibilityCheck --> CustomerTypeCheck{Customer Type & Status?}
    
    %% Non-Eligible Paths with Error Pages
    CustomerTypeCheck -->|Electricity-Only Customer| ErrorPage1[Specific Error Page]
    CustomerTypeCheck -->|Customer in Retention| ErrorPage2[Specific Error Page]
    CustomerTypeCheck -->|Disconnected Customer| ErrorPage3[Specific Error Page]
    CustomerTypeCheck -->|Pending request| PendingRequestPage[Specific Error Page]
    CustomerTypeCheck -->|Failed Eligibility Check| GeneralError[General Error Page]
    
    %% Eligible Path - URL Check for eligible customers
    CustomerTypeCheck -->|Eligible Cable Customer| URLCheck{URL in content system?}
    URLCheck -->|Yes| PromoPage[Promotional Landing Page]
    URLCheck -->|No| PersonalZone[Default Personal Zone]
    
    %% Continue to Static Welcome View
    PromoPage --> StaticWelcomeView["Static View with User Name from API"]
    PersonalZone --> StaticWelcomeView
    StaticWelcomeView --> ContinueButton["Submit Go Ahead Form"]
    
    %% Upgrade Key Verification
    ContinueButton --> UpgradeKeyCheck{"Received Upgrade Key?"}
    UpgradeKeyCheck -->|No| GeneralErrorPage["General Error Page"]
    UpgradeKeyCheck -->|Yes| GetUpgradeDataApiCheck{"GetUpgradeDataApi Valid?"}
    GetUpgradeDataApiCheck -->|No| GeneralErrorPage["General Error Page"]
    GetUpgradeDataApiCheck -->|Yes| DetailsValidation["Personal Details Validation Screen"]
    DetailsValidation --> EmailVerification["Email Verification/Edit Option"]
    DetailsValidation --> AddressDisplay["Customer Address Display"]
    DetailsValidation --> ServiceCategories["Current Service Categories Display"]
    
    %% Details Confirmation
    EmailVerification --> DetailsConfirmation["Confirm Details Button"]
    AddressDisplay --> DetailsConfirmation
    ServiceCategories --> DetailsConfirmation
    
    %% Server Validation after Confirm Details
    DetailsConfirmation --> ServerValidation{"Server Returns Valid Status?"}
    ServerValidation -->|Yes| BandwidthSelection["Bandwidth Selection Screen"]
    ServerValidation -->|No| GeneralErrorPage["General Error Page"]
    
    %% Bandwidth Selection
    BandwidthSelection --> PackageChoice["Customer Selects Bandwidth Package"]
    PackageChoice --> PackageSubmit["Submit Package Selection"]
    PackageSubmit --> PackageSubmitCheck{"Submission Successful?"}
    PackageSubmitCheck -->|Yes| SchedulePage["Schedule Installation Page"]
    PackageSubmitCheck -->|No| GeneralErrorPage["General Error Page"]
    GeneralErrorPage --> CRMErrorCase["Create CRM Case"]
    
    %% Schedule Installation Process
    SchedulePage --> SlotSelection["User Selects Date/Time Slot"]
    SlotSelection --> SubmitSchedule["Submit Selected Time Slot"]
    SubmitSchedule --> ScheduleCheck{"Schedule Submission Check"}
    ScheduleCheck -->|Success| SuccessPage["Installation Scheduled Success Page"]
    SuccessPage --> ConfirmationButton["Confirmation Button"]
    ConfirmationButton --> ConfirmationCheck{"Confirmation Successful?"}
    ConfirmationCheck -->|Yes| DealSummary["Deal Summary Page"]
    ConfirmationCheck -->|No| GeneralErrorPage
    DealSummary --> SendEmail["Send Email with Summary"]
    ScheduleCheck -->|General Error| GeneralErrorPage["General Error Page"]
    ScheduleCheck -->|Time Slot Taken| SlotTakenError["Time Slot No Longer Available Error"]
    SlotTakenError --> SchedulePage
    
    %% CRM Case Creation for Non-Eligible
    ErrorPage1 --> CRMCase1[Create CRM Case]
    ErrorPage2 --> CRMCase2[Create CRM Case]
    ErrorPage3 --> CRMCase3[Create CRM Case]
    GeneralError --> CRMCaseGeneral[Create CRM Case]
    
```

### Process Details:

1. **SMS Campaign**:
   - Marketing sends SMS to Fiber-Ready customers with personalized link
   - SMS content includes promotional message about fiber availability
   - Customer is prompted to click link to begin upgrade process

2. **Eligibility Verification**:
   - Upon entry, system creates process record in database
   - Core systems verify eligibility for one-click upgrade
   - System checks customer type and current status

3. **Non-Eligible Scenarios**:
   - Electricity-only customers → Specific error page + CRM case
   - Customers in retention programs → Specific error page + CRM case
   - Disconnected customers (up to 6 months) → Specific error page + CRM case
   - Customers failing general eligibility → General error page + CRM case

4. **Eligible Customers**:
   - Based on existing one-click upgrade process
   - Customer selects from available fiber packages
   - Only bandwidth change required (no additional payment)
   - Upgrade completed with confirmation
   - System checks session validity
   - If session expired, shows timeout page
   - If valid, proceeds to main promotional content

This is the first step in the customer journey for the Cable to Fiber upgrade process.
