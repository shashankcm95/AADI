# Arrive Platform

> GPS-Powered Just-in-Time Kitchen Orchestration

## Architecture

```
packages/          → Frontend Apps
  customer-web/    → React customer ordering
  admin-portal/    → Admin portal for managing operations
  mobile-ios/      → React Native iOS app

services/          → Backend Microservices
  orders/          → Order lifecycle management
  users/           → User profile management
  restaurants/     → Restaurant data management
  pos-integration/ → Point of Sale integration
  shared/          → Shared Lambda Layer (CORS, auth, serialization, logger)

infrastructure/    → SAM templates, scripts, and AWS infrastructure
```

## Quick Start

```bash
# Install dependencies
npm install

# Start customer web
npm run dev:customer

# Start admin portal
npm run dev:admin

# Start iOS app
npm run dev:ios
```

## Services

| Service | Port | Purpose |
|---------|------|---------|
| Customer Web | 5173 | Customer ordering |
| Admin Portal | 5174 | Admin operations |
| iOS (Expo) | 8081 | Mobile app |

## Tech Stack

- **Frontend:** React, React Native, TypeScript
- **Backend:** Python 3.11, AWS Lambda, DynamoDB
- **Infrastructure:** AWS SAM, API Gateway, Cognito, S3, CloudFront, CloudWatch
- **Shared Layer:** Cross-cutting utilities deployed as a Lambda Layer (CORS, auth, serialization, structured logger)
- **Observability:** CloudWatch metric filters, alarms, and dashboard for order lifecycle and capacity monitoring

## Testing

```bash
# Run all backend suites in isolation (recommended)
python3 -m pytest tests/test_python_suites.py -q

# Run individual service
python3 -m pytest services/orders/tests/ -q
python3 -m pytest services/restaurants/tests/ -q
python3 -m pytest services/users/tests/ -q
python3 -m pytest services/pos-integration/tests/ -q
python3 -m pytest infrastructure/tests/ -q
```