# Engineering Backlog
**Source:** Code review + test audit (2026-02-27)
**Reviewer perspective:** Senior staff developer + product owner
**All 339 tests passing at time of writing.**

---

## Parallelization Guide

Items with no shared files can be worked concurrently. Safe parallel groups:

| Group | Items | Rationale |
|---|---|---|
| A | BL-001, BL-002, BL-006 | Backend-only, different handlers |
| B | BL-003, BL-004, BL-005 | Mobile/API layer, different concerns |
| C | BL-007, BL-008, BL-009 | Cart/order validation, mostly non-overlapping |
| D | BL-012, BL-013, BL-014 | HomeScreen display data — same file but additive changes |
| E | BL-015, BL-016, BL-017, BL-018, BL-019 | All independent low-effort items |
| F | BL-010, BL-011 | Backend infrastructure, different services |
| G | BL-020 | Payment audit — read-only scan first, then targeted removals |

---

## CRITICAL

### BL-001 — Fix price decimal precision in menu ingestion
**Severity:** Critical
**Files:** `services/restaurants/src/handlers/menu.py` ~line 72
**Problem:**
`int(float(price) * 100)` converts a `Decimal` to `float` before multiplying, introducing IEEE 754 rounding errors. `$19.99` can become `1998` cents instead of `1999`. Prices stored in the database may be silently wrong at the cent level.
**Fix:** Replace with `int(price * 100)` using pure Python `Decimal` arithmetic. Ensure the price value being multiplied is a `Decimal`, not a float at any intermediate step.
**Acceptance criteria:**
- `$19.99` → `1999` cents
- `$10.10` → `1010` cents
- `$0.01` → `1` cent
- All existing `test_update_menu_price_parsing` cases still pass, plus new edge-case assertions for the above values.

---

### BL-020 — Payment code audit: remove non-POS payment patterns
**Severity:** Critical (architectural clarity)
**Context:**
Arrive's payment model is **pay-at-restaurant via existing POS only**. Arrive orchestrates kitchen timing — it does not collect or process payments. `price_cents` and `total_cents` fields are informational: they are computed server-side and forwarded to the POS for its records, and displayed on order tracking screens for customer reference. No payment collection or charging happens through Arrive.

**Problem:**
Client-side cart totals are computed in the mobile app and customer web portal. While the backend (`create_session_model()` in `services/orders/src/engine.py`) correctly computes `total_cents` server-side, the presence of client-calculated totals creates confusion about whether Arrive is the payment authority. This must be clarified and cleaned up.

**Scope of changes:**

| File | Action |
|---|---|
| `packages/mobile-ios/src/state/CartContext.tsx` ~line 108 | Keep `cartTotalCents` for **display purposes only** (cart UI). Add a code comment: "Display only — backend recomputes total_cents authoritatively in create_session_model()." |
| `packages/mobile-ios/src/screens/CartScreen.tsx` ~line 134 | Keep per-item subtotal and total display. Add same comment. |
| `packages/customer-web/src/components/Cart.jsx` line 7 | Keep cart total display. Add comment. |
| `services/orders/src/handlers/customer.py` | Verify that `create_order()` never persists a client-supplied `total_cents` — it must use the value from `create_session_model()` only. |
| `tools/mock-server/index.js` lines 105, 241 | Mark with `// DEMO ONLY - not production logic` comment. |

**What NOT to change:**
- `price_cents` fields throughout — these are menu item prices, correct to keep
- `arrive_fee_cents` — server-computed platform reporting field, correct to keep
- `total_cents` on `Order` response interface — correct, this is the server-computed value returned to display

**Acceptance criteria:**
- A code comment audit confirms no client-computed value is ever used as the authoritative order total on the backend
- `create_session_model()` in `engine.py` is the single source of truth for `total_cents`
- No `total_cents` value from a client request body persists to DynamoDB — only the server-computed one
- A comment block is added to `CartContext.tsx` and `Cart.jsx` documenting the display-only intent

---

## HIGH

### BL-002 — Block restaurant self-reactivation
**Severity:** High
**Files:** `services/restaurants/src/handlers/restaurants.py` (RBAC check for PUT /v1/restaurants/{id})
**Problem:**
A restaurant admin whose restaurant has been deactivated by a platform admin can PUT `{"active": true}` against their own restaurant and self-reactivate. The RBAC middleware allows restaurant admins to update their own restaurant record without restricting which fields they can change.
**Fix:** In the restaurant update handler, when the requesting user is a `restaurant_admin` (not a platform admin), strip the `active` field from the request body before processing. Only users with the `admin` role may set `active: true` on a restaurant.
**Acceptance criteria:**
- A `restaurant_admin` PUT with `{"active": true}` on a deactivated restaurant returns 403
- A platform `admin` PUT with `{"active": true}` succeeds
- A `restaurant_admin` can still update other fields (name, address, image_keys, etc.) on their own restaurant
- New test: `test_restaurant_admin_cannot_self_reactivate`

---

### BL-003 — Add GET /v1/restaurants/{id} endpoint + fix mobile restaurant fetch
**Severity:** High
**Files:**
- `services/restaurants/src/handlers/restaurants.py` (add handler)
- `services/restaurants/src/app.py` (add route)
- `packages/mobile-ios/src/services/api.ts` lines 194-204 (`getRestaurant()`)

**Problem:**
`getRestaurant(restaurantId)` in `api.ts` fetches the entire restaurant catalog and does a client-side `.find()` to locate one restaurant. This is called on every MenuScreen and OrderScreen load. Pulling the full catalog for a single-restaurant lookup wastes bandwidth and will degrade as the catalog grows.
**Fix:**
1. Add a `GET /v1/restaurants/{restaurant_id}` route to the restaurants service that returns a single restaurant by ID (DynamoDB `GetItem`, not `Scan`).
2. Update `getRestaurant()` in `api.ts` to call the new endpoint directly.
3. The existing list endpoint remains for the HomeScreen catalog view.
**Acceptance criteria:**
- New endpoint returns 200 with the restaurant object for a valid ID
- New endpoint returns 404 for an unknown ID
- `getRestaurant()` in `api.ts` no longer fetches the full list
- New test: `test_get_single_restaurant_by_id`
- New test: `test_get_single_restaurant_not_found`

---

### BL-004 — Send Idempotency-Key on mobile order creation
**Severity:** High
**Files:**
- `packages/mobile-ios/src/screens/MenuScreen.tsx` (order placement handler)
- `packages/mobile-ios/src/services/api.ts` (`createOrder()`)

**Problem:**
The backend has full idempotency infrastructure (`services/orders/src/handlers/customer.py` reads `Idempotency-Key` header). The mobile client never sends this header. Double-tapping "Place Order" on a slow network creates duplicate orders in the kitchen queue.
**Fix:**
1. In `createOrder()` in `api.ts`, generate a UUID idempotency key (or accept one as a parameter).
2. In `MenuScreen.tsx`, generate the key when the user taps "Place Order" and pass it through. Store the key for the duration of the placement flow so retries reuse it.
3. Key must be stable across retries of the same user action, but must be fresh for a new order attempt.
**Acceptance criteria:**
- `createOrder()` sends `Idempotency-Key: <uuid>` header on every call
- Tapping "Place Order" twice in quick succession results in exactly one order in DynamoDB
- Test: mock two sequential `createOrder` calls with the same key; assert only one network request succeeds (second returns cached/409 response)

---

### BL-005 — Fix location sample circuit breaker (add TTL + reset)
**Severity:** High
**Files:** `packages/mobile-ios/src/services/api.ts` lines 367-408
**Problem:**
A single 404 response from the location sample route sets a module-level `locationSampleRouteUnavailable = true` flag permanently for the app session. If the backend recovers (deploy, config change), the client never retries. For a product whose core value prop is GPS-powered just-in-time kitchen orchestration, silently dropping all location telemetry is a critical failure mode.
**Fix:**
Replace the permanent flag with a timestamped backoff. After a 404, disable for a configurable cooldown period (e.g. 5 minutes). After the cooldown, attempt one probe request. If it succeeds, re-enable the route. If it fails again, extend the backoff (exponential or fixed).
**Acceptance criteria:**
- After a 404, location samples are suppressed for ~5 minutes
- After the cooldown, one probe is attempted
- On probe success, sampling resumes normally
- On probe failure, another cooldown window starts
- Unit tests cover: initial disable, cooldown period, recovery on probe success, re-disable on probe failure

---

### BL-006 — Escape Cognito filter string in restaurant admin lookup
**Severity:** High
**Files:** `services/restaurants/src/handlers/restaurants.py` ~line 146
**Problem:**
The Cognito user filter is built with unescaped string interpolation: `filter_str = f'email = "{contact_email}"'`. A quote character in the email address breaks the filter expression and may cause the Cognito API call to fail or behave unexpectedly.
**Fix:**
Before building the filter string, validate that `contact_email` is a well-formed email address (simple regex: `^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$`). Reject the request with 400 if the format is invalid. Do not attempt to escape quotes — validate input instead.
**Acceptance criteria:**
- Email addresses with quotes or special characters return 400
- Valid email format passes through unchanged
- New test: `test_restaurant_admin_lookup_rejects_malformed_email`

---

## MEDIUM

### BL-007 — Fix CartContext double-setState race in forceAddItemToCart
**Severity:** Medium
**Files:** `packages/mobile-ios/src/state/CartContext.tsx` lines 133-143
**Problem:**
`forceAddItemToCart` calls `setCartItems(...)` and then `setCartRestaurant(...)` as two separate React state updates. In async/setTimeout contexts (outside event handlers), React 18 does not batch these, resulting in a render cycle between the two updates where the cart shows cleared items with the stale restaurant. Visible as a flicker during restaurant switches.
**Fix:** Merge both updates into a single `useReducer` dispatch or use `unstable_batchedUpdates` (React Native) to guarantee atomicity.
**Acceptance criteria:**
- Switching restaurants from a non-empty cart triggers exactly one re-render for the combined state change
- No intermediate render state with cleared items + stale restaurant
- Existing CartContext tests still pass

---

### BL-008 — Fix cart item deduplication for items without IDs
**Severity:** Medium
**Files:** `packages/mobile-ios/src/state/CartContext.tsx` lines 65-72
**Problem:**
The cart uses a composite key of `id|name|price|description` for deduplication. Items with `id = ""` all share the `no-id|name|price|desc` key format. Two different menu items with the same name and price (e.g. "Sauce - Small" and "Sauce - Large" both priced at $2.00 with no description) merge their quantities instead of being tracked separately.
**Fix:** Generate a stable local identifier for items with missing IDs at the point of `getRestaurantMenu()` normalization (the `fallbackId` logic already exists in `api.ts` — ensure it's unique and non-empty). Do not allow empty-string IDs to persist into the cart.
**Acceptance criteria:**
- Two structurally identical items (same name, price, description) with different IDs are tracked independently in the cart
- Items arriving from the API with no ID use the `fallbackId` from `getRestaurantMenu()` — never empty string
- Deduplication only merges items that are genuinely the same (same ID)

---

### BL-009 — Add backend qty validation on order items
**Severity:** Medium
**Files:** `services/orders/src/handlers/customer.py` (`create_order()`)
**Problem:**
`validate_resources_payload()` in `engine.py` tests `qty` is present and `qty > 0` — but the handler calls this correctly, so `qty: 0` and `qty: -1` are already rejected (tests confirm this). However, there is no maximum qty guard. A client can send `qty: 9999` for any item, which passes validation and creates an unreasonable order.
**Fix:** Add a `MAX_ITEM_QTY = 99` constant and reject any item with `qty > MAX_ITEM_QTY` with a 400 response.
**Acceptance criteria:**
- `qty: 99` is accepted
- `qty: 100` is rejected with 400
- New test: `test_create_order_rejects_excessive_qty`

---

### BL-010 — Implement order TTL / expiry for abandoned orders
**Severity:** Medium
**Files:**
- `services/orders/src/engine.py` (`create_session_model()`)
- `services/orders/src/handlers/customer.py`
- `services/restaurants/template.yaml` (OrdersTable definition)

**Problem:**
Orders in PENDING or WAITING status with no further activity are never marked expired. They persist indefinitely in DynamoDB, blocking capacity accounting and polluting the kitchen queue. The `ttl` field already exists on session objects — it is set but not enforced at the application layer, and DynamoDB TTL may not be enabled on the table.
**Fix:**
1. Verify DynamoDB TTL is enabled on the OrdersTable with the `ttl` attribute.
2. In the location ingest handler and vicinity event handler, before processing an event, call `ensure_not_expired()` (already implemented in `engine.py`) and return 410 Gone if the order is expired.
3. Add a scheduled Lambda (EventBridge, 5-minute rate) that scans for PENDING/WAITING orders older than a configurable threshold (default: 4 hours) and transitions them to `expired` status.
**Acceptance criteria:**
- DynamoDB TTL enabled on OrdersTable
- `ensure_not_expired()` called at entry point of all order mutation handlers
- Scheduled expiry job exists and has tests
- Expired orders do not appear in the kitchen queue

---

### BL-011 — Paginate restaurant admin DynamoDB scan
**Severity:** Medium
**Files:** `services/restaurants/src/handlers/restaurants.py` (admin list handler)
**Problem:**
The admin path for listing restaurants performs a full table scan, consuming all paginated results into a single in-memory list before returning. This works now but will become expensive (latency + cost) as the restaurant catalog grows.
**Fix:** Add `limit` (default 50, max 200) and `cursor` (base64-encoded `LastEvaluatedKey`) query parameters to the admin list endpoint. Return `next_cursor` in the response when more pages exist. The existing public list endpoint (non-admin) can be updated in the same PR.
**Acceptance criteria:**
- `GET /v1/restaurants?limit=20` returns 20 restaurants and a `next_cursor`
- `GET /v1/restaurants?cursor=<token>` returns the next page
- When no more pages exist, `next_cursor` is absent from response
- New tests cover pagination boundary conditions

---

### BL-012 — Remove hardcoded delivery times and fees from HomeScreen
**Severity:** Medium
**Files:** `packages/mobile-ios/src/screens/HomeScreen.tsx` ~lines 342-345, ~364
**Problem:**
`index % 2 === 0 ? '20-30 min' : '15-25 min'` and `index % 2 === 0 ? '$1.99' : '$0.99'` produce values with no relationship to actual restaurant data. Users see fabricated estimates, which undermines trust and is misleading.
**Fix:**
- Remove the hardcoded delivery time display entirely. Arrive's model does not include delivery — replace with "Pick up" label or omit the field.
- Remove the hardcoded fee display. The `arrive_fee_cents` is available on the order object after placement — it should not be displayed pre-order. Remove from the restaurant card.
- If prep time estimates are desired, that requires a `prep_time_minutes` field on the restaurant object (a future addition — don't fabricate it now).
**Acceptance criteria:**
- No `index % 2` logic anywhere in HomeScreen
- No fabricated delivery times or fees displayed
- Restaurant cards still render without these fields

---

### BL-013 — Fix restaurant ratings (remove display or wire to real data)
**Severity:** Medium
**Files:**
- `packages/mobile-ios/src/screens/HomeScreen.tsx` (renders `rating`)
- `services/restaurants/src/handlers/restaurants.py` (restaurant object)

**Problem:**
Every restaurant displays `0` stars because `rating` is never populated in the DynamoDB restaurant record or returned by the API.
**Options (choose one):**
A. Remove the rating display from the restaurant card until ratings are implemented as a feature.
B. Add a `rating` field (float, 0.0–5.0) to the restaurant schema, make it admin-settable via PUT, and return it in the API response.

**Recommendation:** Option A now, Option B as a separate feature. Showing 0 stars is worse than showing no stars.
**Acceptance criteria:**
- No `0` star display on any restaurant card
- If field is removed: rating-related code is fully removed from frontend and `OrderItem`/restaurant interfaces
- If field is added: backend validates 0.0 ≤ rating ≤ 5.0

---

### BL-014 — Fix restaurant distance calculation (euclidean → haversine, remove random fallback)
**Severity:** Medium
**Files:** `packages/mobile-ios/src/screens/HomeScreen.tsx` ~lines 250-256
**Problem:**
Two bugs in restaurant list sorting:
1. Euclidean distance on raw lat/lon coordinates is geometrically incorrect (degree-to-meter conversion varies by latitude; error is non-trivial at city scale).
2. When user coordinates are unavailable, distance falls back to `Math.random()`, giving a different sort order on every render.

**Fix:**
1. Replace the distance function with haversine formula. A ~15-line implementation or a lightweight dependency (e.g. `geolib`) is appropriate.
2. Replace `Math.random()` fallback with `Infinity` so restaurants without a calculable distance sort to the bottom rather than randomly.
**Acceptance criteria:**
- Distance calculation uses haversine
- Restaurants sort stably (no random reorder on re-render)
- Missing user location → restaurants sorted by name or pushed to end, not random
- Unit test for haversine calculation with known coordinates

---

## LOW

### BL-015 — Fix optimistic favorite toggle (loading state + unmount safety)
**Severity:** Low
**Files:** `packages/mobile-ios/src/screens/MenuScreen.tsx` lines 126-144
**Problem:**
The heart button flips visually immediately (optimistic). On network failure, it rolls back and shows an Alert. But between flip and rollback, the user may navigate away, causing the rollback to fire on an unmounted component (React warning, potential crash on older RN versions). Also: the button is not disabled during the in-flight request, allowing double-taps to queue multiple requests.
**Fix:**
1. Set a `favoriteUpdating` loading state to `true` before the request and `false` in the finally block.
2. Disable the button while `favoriteUpdating` is true.
3. Use a mounted-ref (`useRef`) to guard the rollback and Alert call — only execute if still mounted.
**Acceptance criteria:**
- Button is non-interactive during the network call
- No React "setState on unmounted component" warning in the logs
- Optimistic flip + rollback behavior is unchanged for the user when they stay on the screen

---

### BL-016 — Remove or implement "Change location" button
**Severity:** Low
**Files:** `packages/mobile-ios/src/screens/HomeScreen.tsx` ~line 331
**Problem:**
The button shows an `Alert.alert('Location', 'Location controls will be added in the next iteration.')` stub. This is visible to users on a production-bound build. Stubs that alert "coming soon" erode trust.
**Fix (choose one):**
A. Remove the button entirely until the feature is ready.
B. Hide it behind a feature flag (environment variable or remote config).
**Recommendation:** Option A. Don't ship UI for features that don't exist.
**Acceptance criteria:**
- No "Location controls will be added in the next iteration" string in any production code path
- Feature flag or removal implemented

---

### BL-017 — Expose XLSX support in admin portal menu ingestion UI
**Severity:** Low
**Files:** `packages/admin-portal/src/components/MenuIngestion.tsx`
**Problem:**
The SheetJS (XLSX) library is already imported and capable of parsing `.xlsx` files, but the file input has `accept=".csv"` and the UI only mentions CSV. Restaurant operators who work in Excel are silently blocked.
**Fix:** Update `accept=".csv,.xlsx,.xls"` and update the UI copy to say "Upload CSV or Excel file".
**Acceptance criteria:**
- `.xlsx` files can be selected and parsed
- UI accurately describes accepted formats
- Existing CSV upload path is unaffected

---

### BL-018 — Add category passthrough test in api.test.ts
**Severity:** Low
**Files:** `packages/mobile-ios/src/services/__tests__/api.test.ts`
**Problem:**
The `getRestaurantMenu` test only exercises the ID fallback logic. The `category` field passthrough fix (introduced 2026-02-27) has no test coverage. A future refactor of the mapper could silently re-drop it.
**Fix:** Add a test case that mocks a response containing `category: 'Mains'` and asserts the returned `OrderItem` has `category === 'Mains'`. Also add a case where `category` is absent from the API response and assert the returned item has `category === ''`.
**Acceptance criteria:**
- `getRestaurantMenu` test suite covers category present, category absent, category empty string
- Tests fail if `category` is removed from the mapper return object

---

### BL-019 — Add observability for MenuScreen fallback categorization
**Severity:** Low
**Files:** `packages/mobile-ios/src/screens/MenuScreen.tsx` lines 61-75
**Problem:**
When a menu item reaches the heuristic fallback (no `category` field, or category is "other"), it is silently bucketed. Now that `category` passes through from the API correctly, this only fires for genuinely uncategorized items from the database. There is no way to know how often this happens or which restaurants have uncategorized menus.
**Fix:** Add a `console.warn` (or structured log) when the heuristic fallback fires: `[MenuScreen] Item "${item.name}" from restaurant ${restaurantId} has no category — using heuristic fallback "${categoryName}"`. This gives visibility in development and can feed a future analytics event.
**Acceptance criteria:**
- Warning logged when fallback fires, including item name and restaurant ID
- Warning NOT logged when item has a valid category from the API
- No warning in tests where mock items have valid categories

---

## Backlog Items NOT on This List (Intentional Deferrals)

| Topic | Reason deferred |
|---|---|
| AWS geofence cutover (shadow mode) | Tracked in `docs/mobile_beta_kanban.md` — awaiting device test SLOs |
| Push notification SDK (expo-notifications Expo Go warning) | Known SDK 53 deprecation, requires dev build — tracked separately |
| Rating system (full feature) | BL-013 handles the display bug; full ratings feature is a product decision |
| Menu versioning / history | Single "latest" version is intentional design for current scale |
| Background location OS suppression | Tracked in `docs/mobile_beta_kanban.md` as Active Risk |
