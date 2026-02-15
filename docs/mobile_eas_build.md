# Mobile EAS Build Runbook

## Files
- `packages/mobile-ios/eas.json`
- `packages/mobile-ios/tsconfig.ci.json`
- `.github/workflows/mobile-eas.yml`

## Required GitHub Secret
- `EXPO_TOKEN`

Generate a token from Expo account settings and add it to repo secrets before running the workflow.

## Build Profiles
- `development`: internal dev-client build
- `preview`: internal beta/TestFlight-style build trigger
- `production`: release build profile with version auto-increment

All profiles use live API environment values:
- `EXPO_PUBLIC_RESTAURANTS_API_URL`
- `EXPO_PUBLIC_ORDERS_API_URL`

## GitHub Workflow Usage
1. Open Actions > `Mobile EAS`
2. Run workflow
3. Select profile (`development` / `preview` / `production`)
4. Choose whether to wait for completion (`wait_for_build`)

`pull_request` and `push` events only run validation checks (config, service tests, app typecheck).  
Only `workflow_dispatch` triggers an EAS iOS build.

## Local Commands
From `packages/mobile-ios`:

```bash
npm run eas:build:ios:dev
npm run eas:build:ios:preview
npm run eas:build:ios:prod
```
