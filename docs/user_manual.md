# Arrive Platform: User Manual

**Version:** 1.0  
**Date:** 2026-02-04

---

## 🚀 Getting Started

Arrive is designed to be easy to run for development. The platform consists of a **Transaction Engine**, **Geo Foundation**, and **Frontend Apps**.

### Prerequisites
- Node.js > 18
- Python > 3.9
- Docker (optional, for AWS SAM local)

### Installation

1.  **Clone the Repository**
    ```bash
    git clone https://github.com/arrive-platform/arrive.git
    cd arrive
    ```

2.  **Install Dependencies** (Root)
    ```bash
    npm install
    ```
    This will install dependencies for the root and all workspaces via Turborepo.

3.  **Setup Environment**
    Copy the example environment file:
    ```bash
    cp .env.example .env
    ```

---

## 🏃‍♂️ Running the Platform

We use **Turborepo** to orchestrate the services. You can start the entire stack with one command, or run individual components.

### Quick Start (Dev Mode)
To spin up the mock server and all frontend apps:

```bash
npm run dev
```

This will run parallel processes:
- **Mock Server:** `http://localhost:3001` (Simulates Backend APIs)
- **Customer Web:** `http://localhost:5173` (Ordering App)
- **Admin Portal:** `http://localhost:5174` (Kitchen Display)
- **iOS Bundler:** `http://localhost:8081` (React Native Metro)

---

## 📱 Using the Applications

### 1. Customer Web App
*The "Ordering" Experience*
1.  Open `localhost:5173`.
2.  **Select a Destination:** Choose from the demo list (e.g., "Burger Joint").
3.  **Add Resources:** Add items to your cart (e.g., "Cheeseburger").
4.  **Checkout:** Enter payment details (Mocked).
5.  **Track:** You will see a "Live Status" screen showing your order progress.

### 2. Admin Portal (KDS)
*The "Fulfillment" Experience*
1.  Open `localhost:5174`.
2.  **Login:** Enter PIN `1234`.
3.  **Dashboard:** You will see the **Dashboard** with active sessions.
    - **Session Cards:** Show status, ETA, and items.
    - **Lanes:** Observe items moving from `Pending` -> `Prep` -> `Cook` -> `Plate`.
4.  **Kanban:** Click "Kanban View" to drag-and-drop items between stages.

### 3. iOS App
*The "Arrival" Experience*
1.  Open Expo Go on your simulator or device.
2.  **Permission:** Allow Location permissions (Select "Allow One Time" for testing).
3.  **Place Order:** Follow the flow.
4.  **Arrival Simulation:**
    - The Mock Server simulates GPS movement.
    - Watch the Admin Portal to see the order auto-fire when the simulated user gets `5 min out`.

---

## 🛠️ Configuration

### Switching Domains
The platform is domain-neutral. To switch from "Dining" to "Logistics":
1.  Edit `shared/types/index.ts`.
2.  Update the `alias` interfaces to match your new domain (e.g., `Restaurant` -> `Warehouse`).
3.  Update the `mock-server/index.js` data to reflect new resource types.

### adding a Service
1.  Create a folder in `services/engine/`.
2.  Add a `README.md`.
3.  Add entry to `package.json` workspaces.

---

## ❓ Troubleshooting

**Q: The order isn't appearing in the Admin Portal.**
A: Ensure the `API_BASE_URL` in `.env` matches the Mock Server URL (default `http://localhost:3001`).

**Q: Location isn't working on iOS.**
A: On Simulator, use *Features > Location > Custom Location* to simulate movement.

**Q: Compilation errors.**
A: Run `python3 -m compileall services/` to verify Python syntax.

---
**Support:** Contact the Platform Team.
