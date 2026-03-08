# CI/CD Guide

This document describes the continuous integration and continuous deployment pipelines for the Arrive platform. Both pipelines are implemented as GitHub Actions workflows stored in `.github/workflows/`. The CI pipeline (`ci.yml`) runs on every push and pull request to the `main` branch. The CD pipeline (`cd.yml`) is currently disabled and will deploy automatically once AWS OIDC credentials are configured in the repository secrets.

---

## Overview of Workflows

Arrive has two workflow files. The CI workflow, named "Arrive CI," validates that backend code is correct, tests pass, the code is lint-clean, and no secrets have been accidentally committed. The CD workflow, named "Arrive CD," builds and deploys the SAM stack to AWS, runs post-deploy smoke tests, builds the frontend applications, syncs them to S3, and invalidates CloudFront caches.

The CI workflow contains three jobs: `backend-check` (active), `frontend-check` (disabled), and `mobile-check` (disabled). Only `backend-check` executes today. The CD workflow contains two jobs: `deploy` (disabled) and `deploy-frontend` (disabled).

---

## The backend-check Job

The `backend-check` job is the heart of the CI pipeline. It runs on `ubuntu-latest` and performs a comprehensive validation of all backend Python services. The job sets three environment variables at the top level that are critical to understand:

```
AWS_DEFAULT_REGION: us-east-1
AWS_ACCESS_KEY_ID: testing
AWS_SECRET_ACCESS_KEY: testing
```

These are dummy credentials. They exist because several libraries in the codebase (notably `boto3`) attempt to read AWS credentials and region at import time. Without these variables, imports fail with a `NoRegionError` or `NoCredentialsError` before any test code runs. The values `testing` are never used to make real AWS calls; all tests mock DynamoDB and other AWS services using the `moto` library or manual mocks.

### Step 1: SAM Template Validation

The first substantive step validates the CloudFormation templates using `sam validate`:

```bash
sam validate --template infrastructure/template.yaml --region us-east-1
sam validate --template services/orders/template.yaml --region us-east-1
sam validate --template services/restaurants/template.yaml --region us-east-1
sam validate --template services/pos-integration/template.yaml --region us-east-1
```

This catches syntax errors, invalid resource types, incorrect intrinsic function usage, and other template-level problems before any code runs. The Users service template is validated implicitly as a nested stack of the root template.

### Step 2: Install Test Dependencies

The pipeline installs Python dependencies from two requirement files:

```bash
pip install -r infrastructure/requirements-dev.txt
pip install -r services/orders/requirements.txt
pip install -r services/restaurants/requirements.txt
```

The `infrastructure/requirements-dev.txt` file contains `pytest`, `ruff`, and `boto3`. Service-specific requirements files add testing libraries like `moto` and any service-level dependencies. The Users and POS services install their own requirements inline in their respective test steps.

### Step 3: Run Orders Engine Tests

```bash
cd services/orders
python -m pytest tests/ -v
```

This runs the Orders service test suite, which contains 229 tests covering order creation, status transitions, capacity management, idempotency, location ingestion, geofence event handling, order expiry, and the leave-time advisory engine.

### Step 4: Run Restaurants Tests

```bash
cd services/restaurants
python -m pytest tests/ -v
```

This runs 121 tests covering restaurant CRUD, menu management, configuration, favorites, image upload URL generation, geofence resync, and admin operations including restaurant admin invitation and linking.

### Step 5: Run Users Service Tests

```bash
cd services/users
pip install -r requirements.txt 2>/dev/null || true
python -m pytest tests/ -v
```

This runs 41 tests covering profile retrieval, profile updates, avatar upload URL presigning, health checks, and CORS header correctness. The `pip install` uses `2>/dev/null || true` because the requirements file may not exist or may have already been satisfied.

### Step 6: Run POS Integration Tests

```bash
cd services/pos-integration
pip install -r requirements.txt 2>/dev/null || true
python -m pytest tests/ -v
```

This runs 76 tests covering API key authentication (SHA-256 hashing, TTL expiry, permission enforcement), order operations via POS, menu sync with empty-item guards, webhook processing, and POS-specific authorization.

### Step 7: Run Isolated Python Suite Gate

```bash
python -m pytest tests/test_python_suites.py -q
```

This is a meta-test that runs each service's test suite in a separate subprocess to detect cross-suite pollution. It ensures that the Orders, Restaurants, Users, POS, infrastructure, and admin logic test suites each pass in complete isolation. This gate was introduced after a module naming collision between the POS service and Python's built-in `posixpath` module caused intermittent failures when suites shared a process.

### Step 8: Run Linter (Ruff)

```bash
ruff check services/orders/src services/restaurants/src services/users/src services/pos-integration/src services/shared/python/shared
```

Ruff is a fast Python linter that checks for style violations, unused imports, unreachable code, and other issues. It lints all service source directories and the shared layer. The configuration is minimal and relies on Ruff's default rule set. Lint failures block the pipeline.

### Step 9: Scan for Secrets

```bash
pip install detect-secrets
detect-secrets scan --baseline .secrets.baseline
detect-secrets audit --report .secrets.baseline
```

The secrets scan uses the `detect-secrets` tool to check the entire codebase for accidentally committed credentials, API keys, or tokens. It compares against a `.secrets.baseline` file that records known false positives. The `audit --report` step verifies that all entries in the baseline have been reviewed. If a new secret-like string is detected, the pipeline fails until the finding is either removed or added to the baseline as a false positive.

---

## Disabled Jobs: frontend-check and mobile-check

Both `frontend-check` and `mobile-check` are disabled with an `if: false` condition at the job level. They are structurally complete but not active.

**frontend-check** would install Node.js 20, run `npm ci`, and then execute `npx turbo run lint build --filter=client --filter=admin-portal` to lint and build both frontend applications. It is disabled because the frontend CI dependencies (Turborepo workspace configuration, npm workspaces) are not yet fully configured for headless CI execution.

**mobile-check** would install Node.js 20, run `npm ci`, and execute the React Native mobile iOS unit tests with `npm run test --workspace=packages/mobile-ios -- --runInBand`. It is disabled for the same reason: the mobile workspace dependencies are not yet configured for CI.

### Re-enabling Disabled Jobs

To re-enable either job, remove the `if: false` line from the job definition in `.github/workflows/ci.yml`. For `frontend-check`, ensure that:

1. The root `package.json` has a `workspaces` field that includes `packages/customer-web` and `packages/admin-portal`.
2. Turborepo is configured with a `turbo.json` at the repository root.
3. Both frontend packages have `lint` and `build` scripts in their `package.json`.

For `mobile-check`, ensure that:

1. The root `package.json` includes `packages/mobile-ios` in its workspaces.
2. The mobile package has a `test` script that runs Jest.
3. Any native dependencies or CocoaPods are not required at the CI level (tests should be pure JavaScript/TypeScript).

---

## The CD Deploy Workflow

The CD workflow (`cd.yml`) triggers on pushes to `main` and is designed to deploy the full stack automatically. It is currently disabled with `if: false` on both jobs.

### The deploy Job

The `deploy` job assumes an IAM role via OIDC federation using `aws-actions/configure-aws-credentials@v2`. The role ARN is read from the repository secret `AWS_DEPLOY_ROLE_ARN`. After assuming the role, it runs `sam build` and `sam deploy` with the `--no-fail-on-empty-changeset` flag targeting the `arrive-dev` stack.

After the SAM deploy completes, the job runs two post-deploy verification steps. First, it executes `scripts/verify_http_api_routes.sh` against each API endpoint to confirm that the expected HTTP routes exist. Second, it acquires a Cognito ID token using the `SMOKE_TEST_USERNAME` and `SMOKE_TEST_PASSWORD` repository secrets, then runs `scripts/smoke_authenticated_order_flow.sh` to exercise the authenticated order creation flow against the live deployment.

### The deploy-frontend Job

The `deploy-frontend` job depends on the `deploy` job completing successfully. It builds both frontend applications with Turborepo, syncs the build outputs to their respective S3 buckets, and invalidates both CloudFront distributions.

### Configuring Secrets for CD

To enable the CD pipeline, you need to configure the following GitHub repository secrets:

**AWS_DEPLOY_ROLE_ARN** must contain the ARN of an IAM role that trusts the GitHub OIDC provider and has permissions to deploy CloudFormation stacks. Follow the AWS documentation for configuring OIDC identity providers for GitHub Actions.

**SMOKE_TEST_USERNAME** and **SMOKE_TEST_PASSWORD** must contain the credentials of a Cognito user in the target environment. This user is used for post-deploy smoke tests. Create the user in the Cognito User Pool and ensure it has the `customer` role.

Once these secrets are configured, remove the `if: false` lines from both the `deploy` and `deploy-frontend` jobs in `.github/workflows/cd.yml`.

---

## Fixing Common CI Failures

### NoRegionError During Tests

If you see `botocore.exceptions.NoRegionError: You must specify a region` in a test step, it means the `AWS_DEFAULT_REGION` environment variable is not set. Locally, export it before running tests:

```bash
export AWS_DEFAULT_REGION=us-east-1
export AWS_ACCESS_KEY_ID=testing
export AWS_SECRET_ACCESS_KEY=testing
```

In CI, these are set at the job level and should not need modification.

### Ruff Lint Failures

Ruff failures produce output showing the file, line number, and rule code. Fix the violations in your source code and commit. Common issues include unused imports (F401), undefined names (F821), and line-length violations (E501). Run `ruff check --fix` locally to auto-fix safe violations.

### detect-secrets Baseline Drift

If the secrets scan fails with a message about the baseline being out of date, regenerate it:

```bash
detect-secrets scan > .secrets.baseline
detect-secrets audit .secrets.baseline
```

During the audit, mark each finding as either a true positive (remove the secret from the code) or a false positive (the tool records your decision in the baseline). Commit the updated `.secrets.baseline` file.

### POS Test Module Collision

The POS service directory previously caused a collision with Python's `posixpath` module because `services/pos-integration` was importable as `pos`. This was resolved by running each test suite in isolation via the `test_python_suites.py` meta-test. If you add a new service, add its test directory to the `SUITES` list in `tests/test_python_suites.py` to ensure it is covered by the isolation gate.
