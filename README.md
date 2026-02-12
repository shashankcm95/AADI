```markdown
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
  kitchen/         → Kitchen operations
  restaurants/     → Restaurant data management
  pos-integration/ → Point of Sale integration

infrastructure/    → SAM templates, scripts, and AWS infrastructure
tools/             → Mock server, dev utilities
```

## Quick Start

```bash
# Install dependencies
npm install

# Start mock server
npm run dev:mock-server

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
| Mock Server | 3001 | Development API |
| Customer Web | 5173 | Customer ordering |
| Admin Portal | 5174 | Admin operations |
| iOS (Expo) | 8081 | Mobile app |

## Tech Stack

- **Frontend:** React, React Native, TypeScript
- **Backend:** Python, AWS Lambda, DynamoDB
- **Infrastructure:** AWS SAM, API Gateway
```