# Deployment Guide

This document describes how to build, configure, and deploy the Arrive platform from a local workstation. It covers prerequisite tooling, the SAM backend stack, frontend static assets, environment-specific configuration, and the feature toggles that control optional subsystems.

---

## Prerequisites

Before attempting a deployment you must have the following tools installed and available on your PATH.

**AWS CLI v2** is required for all interactions with your AWS account. Verify with `aws --version`; the minimum supported version is 2.x. You must have a named profile or environment variables configured with credentials that have permission to create and update CloudFormation stacks, S3 buckets, DynamoDB tables, Lambda functions, Cognito user pools, CloudFront distributions, and IAM roles. If you are deploying to a shared account, confirm that your credentials carry the `CAPABILITY_IAM` authorization that SAM requires.

**AWS SAM CLI** is required for building and deploying the serverless backend. Install it from the AWS documentation or via Homebrew on macOS with `brew install aws-sam-cli`. Verify with `sam --version`; the minimum supported version is 1.90 or later. SAM CLI orchestrates the CloudFormation deployment, packages Lambda code, and manages nested stack uploads.

**Python 3.11** is the Lambda runtime for every backend function. You need a local Python 3.11 installation so that `sam build` can resolve dependencies and compile the shared layer. Using a different minor version may produce incompatible bytecode or dependency mismatches. If you manage multiple Python versions, tools such as `pyenv` can simplify switching.

**Node.js 20** and **npm** are required for building the two frontend applications (customer-web and admin-portal). Both are Vite/React single-page applications that produce static bundles deployed to S3. Verify with `node --version` and `npm --version`.

---

## AWS Account Setup

If you are deploying Arrive into a fresh AWS account for the first time, confirm the following before running `sam deploy`.

The account must have the Amazon Location Service available in the target region. Arrive provisions an Amazon Location Tracker and a Geofence Collection as part of the root stack. The default deployment region is `us-east-1`, and all CI/CD workflows reference that region.

The Cognito User Pool created by the stack requires a unique domain prefix. The template generates this from the stack name and account ID (`${StackName}-auth-${AccountId}`), so domain collisions are unlikely, but be aware that Cognito domain names are globally unique within a region.

S3 bucket names are also globally unique. The template constructs bucket names using the pattern `${StackName}-<purpose>-${AccountId}`. If a bucket with the same name already exists in any account worldwide, the stack creation will fail. Choose a stack name that is unlikely to collide.

---

## Deploying the SAM Backend Stack

All backend infrastructure is declared in `infrastructure/template.yaml`. This root stack creates shared resources (Cognito, CloudFront, S3 hosting buckets, Amazon Location, the shared Lambda layer) and nests three child stacks for the Orders, Restaurants, and Users services. A fourth child stack for POS Integration is conditionally deployed based on a parameter toggle.

### Building

From the repository root, run the build step:

```bash
cd infrastructure
sam build
```

SAM CLI reads each `AWS::Serverless::Function` resource, resolves its `CodeUri`, installs Python dependencies from any `requirements.txt` it finds in the code directory, and packages the result into `.aws-sam/build/`. The shared Lambda layer at `services/shared` is also built and packaged. The build step must complete without errors before you attempt a deploy.

If you encounter build failures related to missing native dependencies, confirm that you are running Python 3.11 and that your pip installation can resolve packages for the `arm64` architecture specified in the templates.

### Deploying

For a first-time deployment, use the guided mode to create a `samconfig.toml` that records your parameter choices:

```bash
sam deploy --guided --capabilities CAPABILITY_IAM
```

SAM will prompt you for a stack name (for example, `arrive-dev`), AWS region, and values for each template parameter. Once `samconfig.toml` exists, subsequent deployments can use the shorter form:

```bash
sam deploy --no-fail-on-empty-changeset --capabilities CAPABILITY_IAM
```

The `--no-fail-on-empty-changeset` flag is recommended so that deploys exit cleanly even when only frontend assets have changed and the infrastructure template is identical.

### First-Time Setup vs. Updates

During the first deployment, CloudFormation provisions all resources from scratch. This includes creating DynamoDB tables, S3 buckets, the Cognito User Pool, CloudFront distributions, and every Lambda function. The initial deployment typically takes eight to twelve minutes because CloudFront distribution creation is inherently slow.

Subsequent updates are faster because CloudFormation only modifies resources whose definitions have changed. When updating only Lambda function code, the deploy usually completes in two to three minutes.

If a deployment fails partway through and the stack enters a `ROLLBACK_IN_PROGRESS` or `UPDATE_ROLLBACK_COMPLETE` state, you can retry the deployment. CloudFormation will attempt to roll forward. If the stack is in `CREATE_FAILED` for a first-time deploy, you may need to delete the stack entirely and redeploy.

---

## CloudFormation Parameters

The root template accepts the following parameters. Understanding each one is essential for configuring Arrive correctly across environments.

**GoogleClientId** and **GoogleClientSecret** are placeholders for Google OAuth federation. The Google identity provider is not yet provisioned in the Cognito configuration, so these parameters exist for future use. You must still provide values (any non-empty string) because they have no default. In practice, pass a placeholder such as `PLACEHOLDER_CLIENT_ID` and `PLACEHOLDER_CLIENT_SECRET`.

**LocationGeofenceCutoverEnabled** controls whether AWS Location geofence ENTER events can authoritatively transition orders from their pending or waiting states. When set to `false` (the default), geofence events are processed in shadow mode only -- they are logged and recorded but do not change order state. Set this to `true` only after you have validated geofence accuracy in your deployment region.

**LocationGeofenceForceShadow** is an emergency rollback switch. When set to `true`, it forces the geofence event consumer back into shadow mode even when cutover is enabled. This allows you to disable geofence-driven transitions without redeploying the stack. Under normal operation, leave this at `false`.

**DeployPosIntegration** controls whether the POS Integration nested stack is created. The default is `false`. Set it to `true` when you are ready to accept inbound API traffic from point-of-sale systems. When set to `false`, no POS-related resources (API Gateway, DynamoDB tables, Lambda function) are provisioned, saving cost and reducing the stack's surface area.

**CorsAllowOrigin** and **CorsAllowOriginAdmin** are passed through to each nested service stack as environment variables. They control the `Access-Control-Allow-Origin` header returned by every Lambda function. In production, these should be the CloudFront distribution URLs for the customer-web and admin-portal applications respectively. During local development, the services also accept `http://localhost:5173` and `http://localhost:5174` as hardcoded fallback origins.

---

## Deploying Frontend Applications

The two frontend applications are built separately and deployed as static assets to S3.

### Customer Web

```bash
cd packages/customer-web
npm ci
npm run build
```

This produces a `dist/` directory containing the optimized Vite build output. Deploy it to the Customer Web S3 bucket:

```bash
aws s3 sync dist/ s3://<CustomerWebBucketName> --delete
```

The bucket name is available in the CloudFormation stack outputs as `CustomerWebBucketName`. After the sync, invalidate the CloudFront cache so users see the latest version:

```bash
aws cloudfront create-invalidation \
  --distribution-id <CustomerWebDistributionId> \
  --paths "/*"
```

The distribution ID is available in the stack outputs as `CustomerWebDistributionId`.

### Admin Portal

The process is identical for the admin portal:

```bash
cd packages/admin-portal
npm ci
npm run build
aws s3 sync dist/ s3://<AdminPortalBucketName> --delete
aws cloudfront create-invalidation \
  --distribution-id <AdminPortalDistributionId> \
  --paths "/*"
```

### Frontend Configuration

Both frontend applications need to know the API endpoint URLs, the Cognito User Pool ID, and the Cognito Client ID. These values come from the CloudFormation stack outputs. You typically write them into an environment file (`.env` or `aws-exports.js`) before running the build. The exact variable names depend on the frontend's Amplify or Vite configuration, but the key outputs to extract are `OrdersApiUrl`, `RestaurantsApiUrl`, `UsersApiUrl`, `UserPoolId`, `UserPoolClientId`, and the CloudFront domain names.

---

## Environment-Specific Configuration

Arrive does not have a formal `Environment` parameter in the current template, but you achieve environment separation through the stack name and parameter values. For example:

For a **development** environment, deploy a stack named `arrive-dev` with CORS origins pointing to localhost or the dev CloudFront domains. Set `DeployPosIntegration` to `false` and both geofence toggles to `false`.

For a **staging** environment, deploy a stack named `arrive-staging` with CORS origins pointing to the staging CloudFront domains. Enable POS integration if you need to test POS flows. Keep geofence cutover disabled and use shadow mode for validation.

For a **production** environment, deploy a stack named `arrive-prod` with CORS origins pointing to the production CloudFront domains. Enable POS integration and, once validated, enable geofence cutover.

Each stack name produces a unique set of resource names (DynamoDB tables, S3 buckets, Cognito pools), so multiple environments can coexist in the same AWS account without collisions.

---

## The DeployPosIntegration Toggle

The POS Integration service is an optional nested stack controlled by the `DeployPosIntegration` parameter. When set to `true`, CloudFormation provisions the `PosIntegrationApi` (a dedicated HTTP API Gateway with throttle limits of 100 burst and 50 requests per second), the `PosApiKeysTable` and `PosWebhookLogsTable` DynamoDB tables, and the `PosIntegrationFunction` Lambda. The POS service receives cross-service table references (OrdersTableName, MenusTableName, CapacityTableName) from the Orders and Restaurants stacks via parameter passing.

When set to `false`, none of these resources are created. The rest of the platform operates normally. This toggle exists because POS integration was rolled out incrementally and may not be needed in every deployment. Switching from `false` to `true` adds the resources on the next deploy. Switching from `true` back to `false` removes them, which means the POS DynamoDB tables and their data will be deleted. If you need to disable POS traffic without losing data, consider keeping the toggle enabled and revoking API keys instead.

---

## The Geofence Cutover Toggles

Arrive uses Amazon Location geofences to detect when a customer physically arrives at a restaurant. The two geofence parameters provide a safe rollout mechanism.

During the initial rollout, set `LocationGeofenceCutoverEnabled` to `false`. Geofence events will still flow through EventBridge to the `GeofenceEventsFunction`, but the consumer will operate in shadow mode: it logs events and writes records to the `GeofenceEventsTable` without transitioning order state. This lets you verify that geofences are firing correctly and at the right locations.

When you are confident in geofence accuracy, set `LocationGeofenceCutoverEnabled` to `true`. The geofence consumer will now authoritatively transition orders when an ENTER event is received.

If a problem arises in production after cutover (for example, false-positive ENTER events due to GPS drift), set `LocationGeofenceForceShadow` to `true`. This immediately reverts the consumer to shadow mode without requiring a full parameter change and redeploy of `LocationGeofenceCutoverEnabled`. Once the issue is resolved, set `LocationGeofenceForceShadow` back to `false`.

Both toggles can be changed via `sam deploy` with updated parameter values. The change takes effect on the next Lambda cold start because the values are passed as environment variables.
