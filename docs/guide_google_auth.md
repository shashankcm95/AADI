```markdown
# How to Setup Google OAuth for Arrive API

This guide explains how to generate the `GoogleClientId` and `GoogleClientSecret` required for deployment, and how to finalize the configuration after deployment (The "Chicken & Egg" workflow).

## Phase 1: Get the Keys (Before Deployment)

1.  **Go to Google Cloud Console**: [https://console.cloud.google.com/apis/credentials](https://console.cloud.google.com/apis/credentials)
2.  **Create a Project**: If you don't have one, create a new project (e.g., "Arrive-Staging").
3.  **Configure OAuth Consent Screen**:
    *   Select **External** (or Internal if you have a Google Workspace org).
    *   Fill in App Name ("Arrive API"), Support Email, etc.
    *   Add `amazoncognito.com` to **Authorized Domains** (or skip if not asked yet; you might need to come back here).
    *   Click Save/Next until finished.
4.  **Create Credentials**:
    *   Click **+ CREATE CREDENTIALS** -> **OAuth client ID**.
    *   **Application Type**: "Web application".
    *   **Name**: "Cognito Staging".
    *   **Authorized JavaScript Origins**: Leave empty or add `http://localhost:3000` for local testing.
    *   **Authorized Redirect URIs**: 
        *   Add `http://localhost:3000/callback` (for local testing).
        *   *Note: We will add the Amazon Cognito URL here in Phase 2.*
    *   Click **Create**.
5.  **Copy the Keys**: 
    *   Copy **Your Client ID**.
    *   Copy **Your Client Secret**.
    *   **Keep these safe.** You will paste them when running `sam deploy --guided`.

## Phase 2: Deploy & Finalize (After Deployment)

1.  **Deploy the Stack**:
    ```bash
    sam deploy --guided
    # Paste your Client ID and Secret when prompted.
    ```
2.  **Get the Cognito Domain**:
    *   Look at the `Outputs` section of the SAM deployment results.
    *   Find the value for `AuthUrl` or `UserPoolId`.
    *   Construct your Callback URL. It usually looks like:
        `https://<stack-name>-auth-<account-id>.auth.<region>.amazoncognito.com/oauth2/idpresponse`
        
        *Wait! The exact URL you need to paste into Google is:*
        `https://<your-cognito-domain>/oauth2/idpresponse`
        
        You can find the "Cognito Domain" in the AWS Console -> Cognito -> User Pools -> [Your Pool] -> App Integration -> Domain name.

3.  **Update Google Console**:
    *   Go back to [Google Credentials](https://console.cloud.google.com/apis/credentials).
    *   Edit your "Cognito Staging" client.
    *   Under **Authorized Redirect URIs**, ADD the Cognito IDP URL:
        `https://<your-cognito-domain>/oauth2/idpresponse`
    *   Click **Save**.

## Phase 3: Testing

1.  Open the `AuthUrl` (from SAM Outputs) in a browser.
2.  You should see the "Sign in with Google" button.
3.  Click it. If Google redirects you back to your App (or the `/callback` endpoint), it works!

## FAQ: Mobile Apps (iOS/Android)

**Q: Why "Web Application" type? We are building a Mobile App.**
A: These credentials are for **Cognito itself** (a server-side entity) to talk to Google.
*   **Hosted UI Flow**: Your mobile app opens a browser view (SFSafariViewController/Chrome Custom Tabs) to the Cognito URL. This uses the "Web" credentials perfectly and is the recommended secure pattern (RFC 8252).
*   **Native SDK Flow**: If you later decide to use the native Google Sign-in SDKs, you will create separate iOS/Android Client IDs in Google Console and simply specify them in the Cognito Identity Provider settings. You do **not** need to change the setup we made today; you just add to it.
```