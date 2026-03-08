# Troubleshooting Guide

This document provides diagnostic procedures for common problems encountered when developing, testing, deploying, and operating the Arrive platform. Issues are organized by category: local development, test failures, deployment problems, runtime errors, mobile-specific issues, and rollback procedures.

---

## Local Development Issues

### NoRegionError on Import

When running tests or invoking Lambda handlers locally, you may encounter `botocore.exceptions.NoRegionError: You must specify a region`. This happens because `boto3` attempts to read the AWS region from the environment or credentials file at import time, before any mock or test fixture has a chance to intercept the call.

The fix is to set three environment variables before running any Python code that imports service modules:

```bash
export AWS_DEFAULT_REGION=us-east-1
export AWS_ACCESS_KEY_ID=testing
export AWS_SECRET_ACCESS_KEY=testing
```

These values are dummy credentials. They are never used for real AWS calls because all tests mock AWS services. The CI pipeline sets these at the job level, but local development environments require them to be set manually or added to your shell profile.

If you are using an IDE like PyCharm or VS Code, you can set these in your run configuration's environment variables rather than exporting them globally.

### Missing Shared Layer Imports

When running service code locally, you may see `ModuleNotFoundError: No module named 'shared'`. The shared Lambda layer at `services/shared/python/shared/` is automatically available to Lambda functions in AWS because it is attached as a layer, but locally you need to make it importable.

The recommended approach is to ensure that `services/shared/python` is on your `PYTHONPATH`. You can do this by setting the environment variable:

```bash
export PYTHONPATH="${PYTHONPATH}:$(pwd)/services/shared/python"
```

Alternatively, each service's test suite typically handles this by inserting the shared layer path into `sys.path` in its `conftest.py`. If you are running a handler directly outside of `pytest`, you will need the `PYTHONPATH` approach.

### Import Errors in POS Service

The POS Integration service is located at `services/pos-integration/`. Because this directory name starts with `pos`, Python's import machinery can confuse it with the `posixpath` module from the standard library under certain conditions. This was the root cause of intermittent test failures that led to the creation of the isolated suite gate in CI.

If you encounter `ImportError` or unexpected module resolution when working with the POS service, ensure you are running its tests from the correct working directory:

```bash
cd services/pos-integration
python -m pytest tests/ -v
```

Running `python -m pytest` from the repository root with the POS test path can trigger the collision if other service tests have already been collected in the same process. The isolated suite gate (`tests/test_python_suites.py`) catches this by running each suite in a separate subprocess.

### SAM Local Invoke Issues

When using `sam local invoke` or `sam local start-api`, the SAM CLI builds a Docker container with the Lambda runtime. Common issues include Docker not running (ensure Docker Desktop is started), the shared layer not being found (ensure `sam build` has been run first), and environment variables not being passed (use `--env-vars` with a JSON file or `--parameter-overrides` to set template parameters).

For nested stack functions, you must invoke them directly by their logical resource name within the child template, not the root template. Consult the SAM documentation for the exact syntax.

---

## Test Failures

### Module Collision Between Test Suites

If a test suite passes when run in isolation but fails when run together with other suites (for example, via `pytest tests/` from the repository root), the likely cause is a module naming collision. The most common manifestation is the POS service's directory conflicting with Python's built-in modules.

The solution is to always run each service's tests from its own directory or rely on the isolated suite gate. If you need to add a new service, add its test directory to the `SUITES` list in `tests/test_python_suites.py`:

```python
SUITES = [
    ["services/orders/tests"],
    ["services/pos-integration/tests"],
    ["services/restaurants/tests"],
    ["services/users/tests"],
    ["infrastructure/tests"],
    ["tests/unit/test_admin_logic.py"],
    # Add new suites here
]
```

### Missing Mocks for DynamoDB Tables

Tests that interact with DynamoDB use the `moto` library to create mock tables. If a test fails with `ResourceNotFoundException` or a similar DynamoDB error, it typically means the mock table was not created in the test fixture.

Check the test's `conftest.py` for the table creation fixture. Each mock table must be created with the same attribute definitions, key schema, and GSIs as the real table defined in the service's `template.yaml`. If a template change adds a new GSI or changes a key schema, the corresponding mock table in the test fixtures must be updated to match.

### Config Table Not Mocked

Some tests (particularly idempotency and order validation tests) depend on the `ConfigTable` or `RestaurantConfigTable` being populated with specific configuration values. If these tables are not mocked or are empty, validation logic may silently pass (if it treats missing config as permissive) or fail with an unexpected error.

Verify that the test fixture creates the config table and populates it with the minimum required configuration. Look for fixtures named `config_table` or `restaurant_config` in the test's `conftest.py`.

### Assertion Failures in Authorization Tests

Authorization tests verify that endpoints return the correct HTTP status code for different roles. A common pattern is asserting that a response is not 403 (meaning the request was not forbidden). If the assertion is `assert status != 403` but the response is actually a 500 (server error), the test passes even though the endpoint is broken.

These weak assertions were identified and strengthened during Phase 11 of the code review. If you encounter a test with `!= 403` assertions, consider strengthening it to `assert status == 200` or the specific expected success status code.

---

## Deployment Issues

### SAM Build Failures

`sam build` can fail for several reasons. The most common is a Python version mismatch: the template specifies `python3.11` and `arm64` architecture, so SAM tries to build for that target. If your local Python is a different version, the build may fail or produce incompatible dependencies.

Another common build failure is a missing `requirements.txt` in a function's `CodeUri` directory. SAM expects to find this file to install dependencies. If the function has no external dependencies, create an empty `requirements.txt` file.

If `sam build` fails on a native dependency (a package with C extensions), ensure you have the appropriate build tools installed. On macOS, this typically means Xcode Command Line Tools.

### CloudFormation Parameter Mismatches

When updating a stack, CloudFormation validates that all required parameters have values. If you add a new parameter to a template without a default value, existing stacks will fail to update unless you provide the new parameter value.

The `GoogleClientId` and `GoogleClientSecret` parameters in the root template have no defaults. If you are deploying for the first time using `sam deploy --guided`, you will be prompted for values. For subsequent non-guided deployments, ensure these parameters are in your `samconfig.toml` or passed via `--parameter-overrides`.

### S3 Bucket Naming Conflicts

S3 bucket names are globally unique across all AWS accounts. The template constructs bucket names as `${StackName}-<purpose>-${AccountId}`. If a bucket with the same name already exists anywhere in AWS, the stack creation will fail with a `BucketAlreadyExists` error.

To resolve this, either choose a different stack name or modify the bucket name pattern in the template. Since bucket names are deterministic based on stack name and account ID, this conflict is rare in practice but can occur if someone else has deployed with the same stack name in a different account.

### Nested Stack Update Failures

When a nested stack update fails, CloudFormation rolls back the entire root stack. The rollback error message in the CloudFormation console often points to the nested stack but does not show the root cause. To diagnose, navigate to the nested stack in the CloudFormation console (it appears as a separate stack with a generated name) and check its Events tab for the specific failure reason.

Common nested stack failures include resource limit exceeded (too many DynamoDB GSIs, too many Lambda functions), timeout (a custom resource Lambda took too long), and invalid parameter values (a reference to a resource that does not exist in the parent stack's outputs).

---

## Runtime Issues

### CORS Errors in the Browser

If the frontend applications show CORS errors in the browser console, the most likely causes are:

The `CORS_ALLOW_ORIGIN` and `CORS_ALLOW_ORIGIN_ADMIN` environment variables on the Lambda functions do not match the actual CloudFront domain names. After a first deploy, the CloudFront domains are generated and may differ from any placeholder values. Redeploy the stack to propagate the correct domain names.

The browser is sending requests from a domain that is not in the allowed origins list. During development, ensure you are accessing the frontend at `http://localhost:5173` or `http://localhost:5174`, which are the hardcoded fallback origins.

An error response from the Lambda (a 500 or unhandled exception) may not include CORS headers, causing the browser to report it as a CORS error instead of showing the actual error. Check the Lambda's CloudWatch logs for exceptions during the same time period.

### 401 Unauthorized Responses

A 401 response means the JWT token is missing, expired, or invalid. Check that the frontend is sending the `Authorization: Bearer <token>` header. Verify that the token has not expired (Cognito ID tokens have a 1-hour default lifetime). Ensure that the API Gateway's JWT authorizer is configured with the correct User Pool ID and Client ID.

If the error occurs only for a specific user, check whether the user's account is disabled or if their email is unverified. Cognito may issue tokens for unverified accounts in some configurations, but the platform may reject them at the application level.

### 403 Forbidden Responses

A 403 response means the user is authenticated but lacks the required role for the operation. Check the user's `custom:role` attribute in Cognito. If the role is missing or set incorrectly, an admin can update it using the Cognito console or the `AdminUpdateUserAttributes` API.

For restaurant_admin users, a 403 can also mean the `custom:restaurant_id` attribute does not match the restaurant ID in the request path. Verify that the restaurant admin is linked to the correct restaurant.

### Capacity Exhaustion

If order creation fails with a capacity error, the restaurant's capacity slots for the current time window are full. Check the `CapacityTable` for the restaurant's current capacity records. Each record has a `window_start` timestamp and a count of active orders in that window.

If capacity appears stuck (showing full even when no orders are active), the `ExpireOrdersFunction` may have failed. Check its CloudWatch logs for errors. This scheduled function runs every 5 minutes and transitions expired PENDING/WAITING orders, freeing their capacity slots.

---

## Mobile-Specific Issues

### Background Location Permissions on iOS

The Arrive mobile app uses location services to confirm the customer's presence at the restaurant. On iOS, the user must grant "Always Allow" location permission for geofence monitoring to work when the app is in the background. If the user selects "While Using the App" or "Never," geofence events will not fire.

To diagnose, check the app's location permission status in iOS Settings. If the permission has been denied, the user must manually re-enable it. The app should prompt for permission with a clear explanation, but iOS limits the number of times an app can re-request permission after a denial.

### Geofence Simulation on iOS Simulator

The iOS Simulator does not support real geofence monitoring. To test geofence-related flows during development, use Xcode's location simulation feature (Debug > Simulate Location) or the GPX file import. This sends simulated GPS coordinates to the simulator, but note that geofence enter/exit events from Amazon Location are processed server-side and require actual position updates via the API.

For end-to-end geofence testing, use a physical device or simulate location updates by calling the `POST /v1/orders/{order_id}/location` API directly with test coordinates.

### Redundant GPS Polling

Earlier versions of the mobile app had an issue where `triggerImmediateVicinityCheck` was called on every 5-second polling cycle, causing redundant GPS reads and double `processLocationUpdate` calls (BL-056). This was fixed by adding a guard that only triggers vicinity checks when the order state changes. If you observe excessive battery drain during order tracking, verify that this guard is in place.

---

## Rollback Procedures

### Geofence Shadow Mode Toggle

If geofence-driven order transitions are causing problems in production (false-positive arrivals, premature state transitions), set the `LocationGeofenceForceShadow` parameter to `true` and redeploy:

```bash
sam deploy --parameter-overrides LocationGeofenceForceShadow=true --no-fail-on-empty-changeset --capabilities CAPABILITY_IAM
```

This immediately forces the geofence consumer into shadow mode on the next cold start. Events continue to be logged to the GeofenceEventsTable but do not transition order state. Manual vicinity reporting via the mobile app continues to work as a fallback.

To revert, set the parameter back to `false` and redeploy.

### POS Integration Toggle

If the POS Integration service is causing issues (throttling downstream services, webhook storms, authentication failures), set `DeployPosIntegration` to `false` and redeploy. This removes the POS API Gateway, Lambda function, and DynamoDB tables entirely. Be aware that this is a destructive operation: data in the PosApiKeysTable and PosWebhookLogsTable will be lost.

For a less destructive approach, consider revoking all POS API keys by deleting their items from the PosApiKeysTable. This disables all POS access without removing the infrastructure.

### CloudFormation Stack Rollback

If a deployment fails and the stack enters an `UPDATE_ROLLBACK_COMPLETE` state, the stack has already been rolled back to its previous configuration. You can retry the deployment after fixing the issue. If the stack is in `UPDATE_ROLLBACK_FAILED`, you may need to use the CloudFormation console to continue the rollback by skipping the failed resources, then retry.

For Lambda function code rollbacks, you can point a function's alias to a previous version. However, since Arrive deploys via SAM without explicit version aliases, the simplest rollback is to revert the code commit and redeploy.

### Frontend Rollback

Frontend deployments are S3 syncs followed by CloudFront invalidations. To roll back a frontend deployment, rebuild the previous version of the frontend from the appropriate git commit and re-sync it to S3:

```bash
git checkout <previous-commit> -- packages/customer-web
cd packages/customer-web
npm ci && npm run build
aws s3 sync dist/ s3://<CustomerWebBucketName> --delete
aws cloudfront create-invalidation --distribution-id <CustomerWebDistributionId> --paths "/*"
```

Repeat for the admin portal if needed. CloudFront invalidation typically propagates globally within 5 to 10 minutes.

---

## Diagnostic Steps Summary

When troubleshooting any issue, follow this general diagnostic flow:

First, identify whether the problem is client-side (browser console errors, mobile app crashes) or server-side (API returning error responses). For client-side issues, check the browser developer tools or mobile app logs for network errors, CORS failures, or JavaScript exceptions.

Second, for server-side issues, check the relevant Lambda function's CloudWatch logs. Use the request's correlation ID (available in the API Gateway response headers as `x-amzn-requestid`) to find all log entries for that request.

Third, check the API Gateway's access logs and metrics for patterns. A sudden spike in 5xx errors across all endpoints suggests an infrastructure issue (IAM permission change, DynamoDB throttling, Lambda concurrency limit). A spike limited to one endpoint suggests a code bug in that handler.

Fourth, check the DynamoDB table metrics for throttling. Although all tables use on-demand billing, rapid traffic increases can temporarily exceed the table's auto-scaled capacity.

Fifth, for issues involving multiple services (for example, order creation failing because restaurant config cannot be read), verify that the cross-service table references are correct. Check that the `RestaurantConfigTableName` parameter in the Orders stack matches the actual table name output from the Restaurants stack. CloudFormation manages these references, but manual parameter overrides in `samconfig.toml` can introduce mismatches.
