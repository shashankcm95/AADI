# Mock Investor Pitch (Simulation Artifact)

Last updated: 2026-02-21
Status: Non-contractual narrative document

## Purpose
This file is a storytelling artifact for product positioning practice. It is not an implementation contract.

## Claims That Match Current Implementation
- Platform focus is timing orchestration, not payment processing.
- Core backend supports staged order lifecycle (`PENDING_NOT_SENT` through completion).
- Capacity gating is implemented in orders service.
- POS integration code exists with API-key auth model and mapping layer.

## Claims That Are Aspirational (Not Fully Deployed By Default)
- POS integration as part of default production stack.
- End-to-end live Google OAuth IdP integration.
- Real-time push channels for kitchen displays (current flow is API/poll based in admin).

## Use Guidance
- Safe for pitch rehearsal and product messaging.
- Do not use this as operational or API documentation.
- For technical truth, use docs under `docs/internal/architecture/`.
