```markdown
# Mock Usage Simulation: "The Perfect Dinner"

**Date:** 2026-02-04
**Scenario:** End-to-End Dining Experience (Order -> Travel -> Arrival -> Handoff)
**Simulated Agents:**
1.  **Chloe (Client Agent):** A hungry user with the iOS App. Driving ETA: 15 mins.
2.  **Marco (Orchestrator Agent):** Expo/Manager at "Arrive Bistro", using the Admin Portal.
3.  **Chef Ramsey (Sub-Agent):** Head Chef, looking at the Kitchen Display.

---

## 🕒 The Timeline

### 18:00 - The Order 📱
**Chloe:** Opens app. Selects "Arrive Bistro". Adds *Signature Truffle Burger* and *Fries*.
**Action:** Taps "Place Order".
**System:**
- Status: `PENDING_NOT_SENT` (Because cooking takes 12 mins, but Chloe is 20 mins away / hasn't left).
- Geo Service: Starts tracking Chloe (Lazy Load triggered).
**Chloe Feedback:** "Okay, order placed. Strange, the app says 'Waiting for you to leave'. Usually it says 'Order Received'."

### 18:05 - The Departure 🚗
**Chloe:** Gets in car. Starts driving.
**System:** Note: GPS detects movement. ETA updating.
**Marco (Admin Portal):** Dashboard shows Upcoming Orders.
**Marco Feedback:** "I see a 'Pending' ticket for Chloe. But it's greyed out. Good, I don't want the kitchen to see it yet and fire it too early."

### 18:12 - The "Firing" Point 🔥
**System:** Chloe is now 12 minutes away. `ETA (12m) == PrepTime (12m)`.
**Event:** `SessionStatus` -> `SENT_TO_DESTINATION`.
**Chef Ramsey:** *Ping!* A new specific ticket appears in the `INIT` (Prep) lane.
**Chef Ramsey:** "Fire 1 Truffle Burger!"
**Marco:** "Perfect timing. We aren't swamped yet."

### 18:20 - The "5 Min Out" Alert ⚠️
**System:** Chloe crosses the 1.5km geofence. `ArrivalStatus` -> `5_MIN_OUT`.
**Marco (Admin Portal):** The ticket on the display starts pulsing/highlighting.
**Chef Ramsey:** Burger is cooking. Moves ticket to `PROCESS` -> `FINALIZE`.
**Marco:** "She's close. Ramsey, plate that burger now."

### 18:24 - Arrival (The Handoff) 🏁
**System:** Chloe enters the parking lot (`PARKING`).
**Chef Ramsey:** Burger is plated and bagged. Status -> `READY`.
**Chloe:** Walks in the door.
**Marco:** Sees Chloe walking in. Looks at the display. Ticket is Green (`READY`).
**Marco:** "Hi Chloe! Burger is right here."
**Chloe:** "Wow, you didn't even have to look for it. And it's hot!"

**System:** Geofence `EXIT` closes active tracking and lifecycle telemetry.

---

## 📝 Post-Simulation Review

### 👤 Chloe (The Client)
**Liked:**
- **The Magic:** "It felt like magic that the food was ready exactly when I walked in. No waiting in the lobby with 10 other delivery drivers."
- **The Exit Signal:** "The exit notification was useful. It confirmed the trip had ended cleanly."

**Change Requests:**
- **Status Anxiety:** "When I first ordered, the 'Waiting for you to leave' status made me nervous. Did the restaurant get it? Maybe change the copy to 'Order Confirmed - We'll start cooking when you head over'."

### 👨‍🍳 Marco (The Staff Orchestrator)
**Liked:**
- **Pacing:** "Normally we get 20 orders at 6pm and the kitchen crashes. This 'Just-in-Time' firing smoothed out the flow. We only cooked what was actually coming."
- **Visibility:** "Knowing she was '5 mins out' let me expedite the fries so they were fresh."

**Change Requests:**
- **Sound Alerts:** "The display needs a louder 'Chime' when the status goes to `5_MIN_OUT`. In a loud kitchen, the visual pulse isn't enough."
- **Manual Override:** "One guy's GPS died and his order never fired. I needed a 'Fire Now' button earlier."

---

## 🚀 Action Items (Derived from Review)
1.  **UX Copy Update:** Change `PENDING_NOT_SENT` user-facing label to "Order Confirmed & Scheduled".
2.  **Feature:** Add "Force Fire" button to Admin Portal for manual override.
3.  **Feature:** Add Audio Cues to the display for arrival events.
```
