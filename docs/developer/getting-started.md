# Getting Started

This guide walks you through setting up the Arrive platform for local development. By the end, you will have every backend service testable and every frontend application running in your browser or simulator.

## Prerequisites

Arrive spans Python backend services, React web applications, and a React Native mobile app. You will need the following tools installed before proceeding.

**Python 3.11 or later** is required for all Lambda services. The runtime target in production is Python 3.11 on arm64, so using that exact version locally eliminates subtle compatibility issues. You can install it via `pyenv` or your system package manager.

**Node.js 20 or later** and **npm 9 or later** are required for the frontend workspaces. The monorepo uses npm workspaces and Turborepo for coordinating builds across packages. Node 18 will work for most tasks, but Node 20 is the tested baseline.

**AWS CLI v2** is needed if you intend to deploy or interact with AWS services directly. Most day-to-day development does not require it, but the SAM CLI depends on it.

**AWS SAM CLI** is the deployment tool for the serverless backend. Install it via `brew install aws-sam-cli` on macOS or follow the official AWS documentation for your platform. You will only need SAM if you are deploying infrastructure changes; running tests and frontends does not require it.

**Expo CLI** is required for the React Native iOS application. Install it globally with `npm install -g expo-cli`, or rely on the local `npx expo` command provided by the workspace dependency.

## Cloning the Repository

Clone the repository and navigate into the project root:

```bash
git clone git@github.com:shashankcm95/AADI.git
cd AADI
```

The working directory for all commands in this guide is the repository root: `/path/to/AADI`.

## Repository Layout

Before installing dependencies, it helps to understand the directory structure. The repository is organized into three primary layers: infrastructure, services, and packages.

```
AADI/
  infrastructure/
    template.yaml          # Root AWS SAM stack (nests child stacks)
  services/
    shared/
      python/shared/       # Lambda Layer: auth, cors, logger, serialization
    orders/
      src/                 # Order engine, handlers, capacity, location bridge
      tests/               # 229 tests
    restaurants/
      src/                 # Restaurant, menu, config, images, geofencing
      tests/               # 121 tests
    users/
      src/                 # Profile management, avatar uploads
      tests/               # 41 tests
    pos-integration/
      src/                 # POS API key auth, webhooks, menu sync
      tests/               # 76 tests
  packages/
    customer-web/          # React/Vite SPA for customers
    admin-portal/          # React/Vite/TypeScript admin dashboard
    mobile-ios/            # React Native/Expo iOS app
  tools/
    mock-server/           # Local mock POS server for development
  scripts/                 # Deployment and utility scripts
  package.json             # Root workspace manifest
```

The `services/shared/python/shared/` directory is a Lambda Layer that every backend service imports at runtime. In tests, each service's `conftest.py` prepends this directory to `sys.path` to simulate the Layer.

## Installing Backend Dependencies

Each Python service manages its own dependencies. There is no single virtual environment for the entire repository; instead, each service has a `requirements.txt` that you install into an isolated environment.

For the orders service:

```bash
cd services/orders
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Repeat for each service you plan to work on:

```bash
cd services/restaurants
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

```bash
cd services/users
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

```bash
cd services/pos-integration
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

The shared layer (`services/shared/`) does not have its own dependencies file because its modules rely only on the Python standard library and `boto3`, which is provided by the Lambda runtime in production and by each service's `requirements.txt` in tests.

## Installing Frontend Dependencies

All frontend packages are managed through npm workspaces from the repository root. A single install at the root handles every workspace:

```bash
cd /path/to/AADI
npm install
```

This installs dependencies for `packages/customer-web`, `packages/admin-portal`, and `packages/mobile-ios` in one pass. The root `package.json` declares all three as workspaces.

## Running the Frontend Applications

The root `package.json` defines convenience scripts for each frontend. All commands should be run from the repository root.

**Customer Web Application** (React/Vite SPA, port 5173 by default):

```bash
npm run dev:customer
```

This starts the Vite development server for the customer-facing web application. Open `http://localhost:5173` in your browser.

**Admin Portal** (React/Vite/TypeScript, port 5174 by default):

```bash
npm run dev:admin
```

The admin portal runs on port 5174 to avoid conflicts with the customer app. Both can run simultaneously.

**Mobile iOS Application** (React Native via Expo):

```bash
npm run dev:ios
```

This launches the Expo development server. You will need either an iOS simulator (via Xcode) or the Expo Go app on a physical device to view the application.

**Mock POS Server** (for testing POS integration locally):

```bash
npm run dev:mock-server
```

This starts a lightweight Node.js server that simulates a point-of-sale system, useful for developing against the POS integration service without a real POS backend.

## Running the Backend Tests

The test suite contains 467 tests across all four services. Each service's tests are self-contained and can be run independently. Tests use `pytest` and mock all AWS dependencies in-memory, so you do not need AWS credentials or a network connection.

**Orders Service** (229 tests):

```bash
cd services/orders
python3 -m pytest tests/ -v
```

**Restaurants Service** (121 tests):

```bash
cd services/restaurants
python3 -m pytest tests/ -v
```

**Users Service** (41 tests):

```bash
cd services/users
python3 -m pytest tests/ -v
```

**POS Integration Service** (76 tests):

```bash
cd services/pos-integration
python3 -m pytest tests/ -v
```

To run all backend tests in sequence from the repository root, you can use a simple loop:

```bash
for svc in orders restaurants users pos-integration; do
  echo "--- Testing $svc ---"
  (cd services/$svc && python3 -m pytest tests/ -v)
done
```

Each service's `conftest.py` handles path setup for the shared Lambda Layer and clears `sys.modules` entries to prevent cross-service module collisions. This means you can run all services in the same pytest session if needed, though running them individually is the standard workflow.

## Running Frontend Tests and Linting

Turborepo coordinates frontend testing and linting across all packages:

```bash
npm test          # Run all frontend tests
npm run lint      # Run all linters
npm run build     # Build all packages for production
npm run clean     # Remove build artifacts and node_modules
```

## Environment Variables

Backend services read configuration from environment variables. In production, these are set by the SAM template. For local testing, the test fixtures mock all DynamoDB tables in-memory, so you generally do not need to set any environment variables to run tests.

If you need to run a Lambda handler locally against real AWS resources (rare during normal development), the key variables are:

```
ORDERS_TABLE=arrive-orders
CAPACITY_TABLE=arrive-capacity
RESTAURANT_CONFIG_TABLE=arrive-restaurant-config
IDEMPOTENCY_TABLE=arrive-idempotency
GEOFENCE_EVENTS_TABLE=arrive-geofence-events
RESTAURANTS_TABLE=arrive-restaurants
MENUS_TABLE=arrive-menus
FAVORITES_TABLE=arrive-favorites
USERS_TABLE=arrive-users
POS_API_KEYS_TABLE=arrive-pos-api-keys
CORS_ALLOW_ORIGIN=http://localhost:5173
CORS_ALLOW_ORIGIN_ADMIN=http://localhost:5174
```

The frontend applications read their API base URL and Cognito configuration from `aws-exports.js` files in each package directory. These are generated during deployment and are not committed to the repository.

## Deploying to AWS

Deployment uses the SAM CLI. From the repository root:

```bash
sam build
sam deploy --guided
```

The guided deployment will prompt you for stack parameters including the Google OAuth client ID and secret, whether to enable geofence cutover, and whether to deploy the POS integration stack.

For subsequent deployments after the initial guided setup:

```bash
sam build && sam deploy
```

The root SAM template (`infrastructure/template.yaml`) creates all shared resources (Cognito, CloudFront, S3, Location Service) and nests child stacks for the Orders, Restaurants, and POS Integration services. The Users service is defined inline in the root template.

## Next Steps

With everything running, you are ready to explore the codebase. The following documentation covers the system in depth:

- **Architecture** explains the serverless design, service boundaries, and request flow.
- **API Reference** documents every endpoint across all four services.
- **Order Lifecycle** details the state machine that drives the core product.
- **Data Model** describes every DynamoDB table, its keys, and access patterns.
- **Authentication and Access Control** covers both Cognito JWT and POS API key auth.
- **Testing Guide** explains the mock patterns and how to write new tests.
- **Glossary** defines every domain term and abbreviation used in the codebase.
