# 00 - Introduction

Version: 3.0
Last updated: 2026-02-21

## What Arrive Is
Arrive is a capacity-aware order dispatch system for restaurant workflows. It separates order creation from dispatch so kitchens are not overloaded when demand spikes.

## Core Product Principle
Dispatch is gated by two signals:
1. Customer arrival intent (`5_MIN_OUT`, `PARKING`, or `AT_DOOR`)
2. Capacity availability in the current time window

## Why This Exists
Without gating, orders can queue too early and degrade restaurant throughput. Arrive deliberately trades immediate dispatch for controlled operational flow.

## Current System Scope
- Customer order creation and tracking
- Restaurant/admin order progression
- Capacity windows with atomic reservation counters
- Advisory endpoint for leave timing (non-reserving)
- Profile, favorites, and restaurant catalog support

## Explicit Non-Goals (Current)
- Payment processing
- Fully automated kitchen workstation scheduling
- Hard real-time push channels for every state change
- POS service auto-deployment in root infra (currently separate)

## Documentation Pointers
- Lifecycle contract: `03-order-lifecycle.md`
- API surface: `04-api-reference.md`
- Data schemas: `06-data-model.md`
- Capacity details: `07-capacity-and-throughput.md`
