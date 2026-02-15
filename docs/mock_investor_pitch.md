```markdown
# Mock Investor Simulation: The "Arrive" Pitch

**Date:** 2026-02-10 (Updated)  
**Participants:**
1.  **Vic (The Investor):** Partner at specialized prop-tech/logistics VC firm. Skeptical, focused on unit economics and "moat".
2.  **Cody (The Tech-Marketer):** Staff SDE turned Growth Lead. Deeply technical but fluent in product-market fit.

---

## 🎙️ The Transcript

**Vic:** Alright Cody, I've seen a dozen "order ahead" apps. Starbucks has one, Chipotle has one. Why do I need *Arrive*? What's the wedge?

**Cody:** Those are great for fast-casual, but the mid-market — the high-end bistros, the family-owned spots, the curbside retailers — they're stuck. They don't have Just-in-Time logistics. Their customers still walk in and wait 20 minutes while the kitchen catches up.

**Vic:** So what does Arrive actually do differently?

**Cody:** We eliminate ordering pipeline wait times. Most "order ahead" apps send the ticket to the kitchen the moment you place the order. Then your food sits under a heat lamp until you show up, or you arrive before it's done.

Arrive flips this. We track the customer's proximity via background GPS, and **fire the kitchen ticket at exactly the right moment** — so the steak finishes at the same second the customer walks through the door. Zero wait, zero heat lamp.

**Vic:** That's a better pitch than "no cold fries." What's the tech architecture?

**Cody:** We're a **timing orchestration layer**, not a payment processor. That's the key insight. We sit between the customer's phone and the restaurant's POS system — Toast, Square, whatever they already use.

The core is a domain-neutral engine. A "Session" is a transaction. A "Destination" is a fulfillment center. We can swap "Burger" for "MRI Machine" and "Restaurant" for "Clinic" in a config file. We have verified this domain neutrality — the code's been refactored and tested.

**Vic:** You said you're not a payment processor. Why not? Seems like leaving money on the table.

**Cody:** It's actually the opposite. Not touching payment data eliminates PCI compliance scope, reduces our liability to near zero, and cuts months from our go-to-market. We support one payment flow today:
1.  **Pay at the restaurant** — they pay at the table. We only handle the timing.

The restaurant's POS system processes all payments. We're infrastructure, not a middleman.

**Vic:** Smart. Lower attack surface. What's the revenue model then?

**Cody:** Split-fee. We charge $0.29 + 1.5% per order, split between the restaurant and the customer. On a $40 check that's $0.89 total — less than a dollar. The restaurant barely notices it, the customer doesn't care, and at scale it's pure margin. The fee is calculated and recorded at order creation, but billed externally — we never touch the money.

**Vic:** I like that. Now, what about the POS integration? Getting into Toast's ecosystem isn't trivial.

**Cody:** We built a dedicated POS Integration Service with a format mapper. Right now it handles Toast, Square, and a generic REST API. Each POS partner gets their own API key — not Cognito JWT — so onboarding is fast. The mapper translates between the POS's native order format and our domain-neutral Session model. Adding a new POS is just adding a new mapper function — maybe 100 lines of code.

**Vic:** How does the GPS work? Apple kills apps for background tracking.

**Cody:** Three key privacy decisions:
1.  **Lazy Loading:** We don't ask for location permission until checkout.
2.  **Blue Bar Transparency:** We use the visible "While Using" background mode so the user *knows* we're tracking. Builds trust.
3.  **Geofence Only:** We don't stream their path to the cloud. We listen for discrete events — `5_MIN_OUT`, `PARKING`, `AT_DOOR`. No breadcrumbs stored.

**Vic:** Less liability. Okay, biggest risk?

**Cody:** Chicken-and-egg with restaurant onboarding. We need restaurants to test the POS integration, but restaurants want to see a working product first. Our plan is to hand-seed three test restaurants, prove the flow end-to-end, then use that demo to onboard the first cohort.

The tech risk is WebSocket latency for the KDS (Kitchen Display). We currently poll every 5 seconds. For scale, we need real-time sockets.

---

## 💡 The Verdict & Feedback

### Vic's Investment Note (The Feedback)

**Strengths:**
1.  **Orchestration, Not Payments:** Not being a payment processor removes PCI scope and lets them focus on what's hard — timing. This is a genuine strategic advantage.
2.  **POS Integration Architecture:** The mapper pattern is clean. Being POS-agnostic means they can ride Toast's and Square's distribution without being locked in.
3.  **Domain Neutrality:** The Session/Destination/Resource abstraction isn't just theoretical — they've refactored the code and have tests proving it. This 10x's the TAM.
4.  **Unit Economics:** The split-fee model at sub-$1 per order is nearly invisible to both sides. High attach rate potential.

**Weaknesses:**
1.  **Cold Start:** Getting the first 50 restaurants is a human problem, not a technical one. Need a strong BD co-founder.
2.  **GPS Dependency:** If Apple restricts background location further, the core value prop degrades. Need a fallback (manual "I'm leaving" button?).

**Decision:**
**✅ INVEST.** The architecture is enterprise-grade from Day 1. The orchestration-not-payments positioning is smart defensibility. The POS integration moat compounds over time.

### Cody's Action Items (Next Steps)
1.  **Demo Day:** Deploy with seeded restaurants and run full pay-at-restaurant flow for investor video.
2.  **WAF:** Enable Web Application Firewall as recommended in the Security Audit.
3.  **Load Test:** Validate DynamoDB capacity under concurrent sessions.
```
