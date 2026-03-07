# Packages Backlog

Deferred architectural and feature work across all packages.
Separate from the code-review backlog (BL-001–BL-070) which is fully resolved.

---

## Admin Portal (`packages/admin-portal/`)

| ID | Priority | Area | Item | Notes |
|----|----------|------|------|-------|
| PKG-001 | High | State Mgmt | Extract Dashboard state into Context or Zustand | 13 state vars + prop drilling |
| PKG-002 | High | Data Fetching | Replace admin order-list fixed 5s poll with React Query/SWR | Dedup, caching, error backoff, stale-while-revalidate. Mobile location polling (sqrt-decay) is already correct. |
| PKG-003 | Medium | Routing | Add React Router for deep linking | Role-based conditional render → proper routes |
| PKG-004 | Medium | Build | Code splitting — lazy load XLSX + Amplify Auth | ~600KB savings on initial load |
| PKG-005 | Medium | Real-Time | WebSocket/SSE for order updates | Replace 5s polling; needed for >50 concurrent users |
| PKG-006 | Medium | Config | Environment-aware aws-exports | Dev/staging/prod configs via Vite env vars |
| PKG-007 | Medium | Backend | Server-side auto-promotion (SENT→IN_PROGRESS) | Currently client-side setTimeout — unreliable |
| PKG-008 | Low | Testing | Vitest + RTL test suite for admin portal | No tests currently |
| PKG-009 | Low | Offline | Network error retry/backoff + stale state indicator | Network blip = silent failure |
| PKG-010 | Low | Pagination | Server-side cursor pagination for orders/restaurants | Requires backend cursor support |
| PKG-011 | Low | Error UX | Error boundary recovery UI (retry button) | Currently shows generic crash screen |
| PKG-012 | Low | CSS | Split 1109-line App.css into component modules | Cosmetic, no correctness gain |

---

## Customer Web (`packages/customer-web/`)

*To be added after review.*

---

## Mobile iOS (`packages/mobile-ios/`)

*To be added after review.*
