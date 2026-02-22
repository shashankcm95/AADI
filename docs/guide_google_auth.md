# Google Auth Integration Guide (Current State)

Last updated: 2026-02-21

## Important Current-State Note
The current `infrastructure/template.yaml` defines `GoogleClientId` and `GoogleClientSecret` parameters, but does not yet provision a Cognito Google Identity Provider resource or attach it to `UserPoolClient`.

Result: Google sign-in is not active in the deployed auth flow today.

## What Is Active Today
- Cognito user pool with email/password auth.
- OAuth Hosted UI for Cognito user pool client.
- Role-based claims (`custom:role`, `custom:restaurant_id`) used by backend authorization.

## If You Want To Enable Google OAuth
1. Create Google OAuth credentials in Google Cloud Console (Web application type).
2. Add Cognito Google IdP resources to infrastructure:
   - `AWS::Cognito::UserPoolIdentityProvider` (provider name `Google`)
   - Include `Google` in `UserPoolClient.SupportedIdentityProviders`
3. Use Cognito callback URL format in Google Console:
   - `https://<cognito-domain>/oauth2/idpresponse`
4. Deploy infra stack and validate Hosted UI sign-in.

## Validation Checklist
- Hosted UI shows Google button.
- Successful Google login returns Cognito tokens.
- Backend routes still enforce role checks via claims.
- Post-confirmation flow still creates/updates profile records correctly.
