# Mobile EAS Build Runbook

Last updated: 2026-02-21

## Source of Truth
- Workflow: `.github/workflows/mobile-eas.yml`
- App config: `packages/mobile-ios/app.json`
- EAS profiles: `packages/mobile-ios/eas.json`

## Supported Build Profiles
- `development`
- `preview`
- `production`

## Required Secret
- `EXPO_TOKEN` in GitHub repository secrets.

## CI Behavior
- On `push`/`pull_request` for mobile paths:
  - installs mobile workspace deps
  - validates Expo config
  - runs selected mobile unit tests
  - runs TypeScript check (`tsconfig.ci.json`)
- On `workflow_dispatch`:
  - runs validation job first
  - then triggers EAS iOS build with selected profile

## Manual Trigger Steps
1. Open GitHub Actions -> `Mobile EAS`.
2. Click `Run workflow`.
3. Choose `profile` and `wait_for_build`.
4. Confirm run.

## Local Commands (from repo root)
```bash
npm ci --workspace=packages/mobile-ios
npm test --workspace=packages/mobile-ios -- --watch=false
npx tsc --project packages/mobile-ios/tsconfig.ci.json --noEmit
npm run eas:build:ios:preview --workspace=packages/mobile-ios
```
