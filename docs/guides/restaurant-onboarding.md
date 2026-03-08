# Restaurant Onboarding Guide

## What Arrive Offers Your Restaurant

Arrive is a restaurant ordering platform built around a simple but powerful idea: food should be ready exactly when the customer walks in. Not before, not after. This is accomplished through real-time location tracking that tells your kitchen when to start cooking based on when the customer is actually approaching your restaurant.

For your restaurant, this means several concrete benefits. Food waste goes down because you are not cooking orders that sit under a heat lamp while the customer is stuck in traffic. Customer satisfaction goes up because every pickup order is fresh. Kitchen throughput improves because the platform controls the flow of orders to match your actual capacity, preventing the rush-hour spikes that overwhelm your line. And staff stress decreases because the system handles the timing and sequencing that your team currently manages by feel and guesswork.

Arrive is not a delivery platform. It focuses exclusively on customer pickup, which means there are no delivery fees to negotiate, no driver coordination headaches, and no middleman between your food and your customer. The customer walks in, picks up their fresh order, and goes. You handle payment at your counter, just as you do today.


## What You Need to Get Started

Getting your restaurant onto Arrive is straightforward. Here is what you will need to provide during the onboarding process.

### Restaurant Information

You will need your restaurant's name, address, and a brief description. The address is important because it is used to set up the geofence zones that detect when customers are approaching. A good description helps customers find and choose your restaurant when browsing the app.

You can also upload images of your restaurant -- photos of the exterior, interior, or signature dishes. These appear on your restaurant listing in the customer app and help attract new orders. Images are uploaded through the Admin Portal and stored securely.

### Your Menu

Arrive needs your menu. The easiest way to get your menu into the system is to prepare a spreadsheet (CSV or Excel format) with four columns: Category, Name, Description, and Price. Each row represents one menu item. For example:

Category could be "Appetizers," "Entrees," "Drinks," or any grouping that makes sense for your restaurant. Name is the item name as you want customers to see it. Description is an optional sentence or two about the item. Price is the item price in dollars (for example, 12.99).

The Admin Portal accepts CSV, XLSX, and XLS file uploads. When you import a file, the system parses it, validates the data, and shows you a preview of what will be imported before you confirm. If any rows have issues (like a missing name or an invalid price), they are flagged and skipped rather than silently dropped.

Prices are stored with full decimal precision using banker's rounding, so you do not need to worry about floating-point rounding errors on prices like $9.95 or $14.50. The system also calculates a machine-safe integer price in cents for internal calculations.

### A Manager Account

Each restaurant on Arrive is managed by a restaurant administrator -- someone on your team who will be responsible for monitoring incoming orders, managing the menu, and configuring settings. During onboarding, an Arrive administrator will create an account for your designated manager. This account is linked specifically to your restaurant, meaning the manager can only see and manage orders and settings for your location.

The manager signs in with an email address and password through the Admin Portal. Their account has the "restaurant_admin" role, which gives them access to the order dashboard, menu management, capacity settings, image uploads, and POS configuration. They do not have access to other restaurants or platform-wide administrative functions.


## How the Platform Works from Your Side

### The Order Lifecycle

When a customer places an order for your restaurant through the Arrive app, here is what happens from your perspective.

First, the order enters a Pending state. You do not see it yet because the customer has not started heading your way. The order is being held by the platform, waiting for the customer to approach. This is the key innovation -- the kitchen is not bothered with orders until the customer is close.

When the customer starts driving toward your restaurant and enters the geofence zone (usually about five minutes away), the platform dispatches the order to your dashboard. The order appears in the "Incoming" lane on your Kanban board, and your dashboard plays an audio notification so your team knows a new order has arrived.

From this point, the order moves through a clear sequence of statuses that your team controls. You move the order to "In Progress" when the kitchen starts working on it. You move it to "Ready" when the food is done. You move it to "Fulfilling" when the customer arrives and you are handing them the order. And you move it to "Completed" when the pickup is finished. There is also a quick-complete option that advances the order through all remaining steps in a single action, which is handy during busy periods.

### Arrival Tracking

As the customer approaches your restaurant, the platform provides progressive updates about their proximity. Your dashboard shows whether the customer is about five minutes away, parking, or at the door. This gives your kitchen a real-time sense of urgency -- if a customer is parking and their order is still in progress, the team knows to prioritize it. If a customer is five minutes out and the order has not been started, there is still plenty of time.

When the customer leaves the vicinity after picking up their order, the platform can automatically complete the order if it is in the Fulfilling state. This reduces the manual bookkeeping your team needs to do at the end of each order.


## Capacity Management

One of the most important features of Arrive for restaurants is capacity management. This system prevents your kitchen from being overwhelmed by controlling how many orders can be active at the same time.

Each restaurant has two configurable parameters. The first is the maximum number of concurrent orders, which defaults to 10. This is the number of orders that can be in active preparation within a single time window. The second is the time window duration, which defaults to 5 minutes (300 seconds). You can also choose 10, 15, or 30-minute windows depending on your kitchen's pace.

Here is how it works in practice. If your maximum is set to 10 and a customer's arrival triggers order dispatch, the system checks whether there are fewer than 10 active orders in the current window. If so, the order is dispatched immediately. If all 10 slots are taken, the order enters a "Waiting for Capacity" state and is queued. As soon as an order completes or a new time window opens, queued orders are dispatched automatically.

You can also configure which geofence zone triggers dispatch. The default is the "5 Minutes Out" zone (about 1,500 meters), but if your kitchen is fast, you might prefer the "Parking" zone (about 150 meters) or even the "At Door" zone (about 30 meters). A coffee shop that can pull an espresso in two minutes might choose "At Door," while a full-service restaurant with complex entrees would stick with "5 Minutes Out."

These settings are adjustable at any time through the Admin Portal's Capacity Settings panel. You can tune them as you learn how the platform works with your specific kitchen operations.


## POS Integration

If your restaurant uses a point-of-sale system like Square, Toast, Clover, or a custom POS, you can optionally connect it to Arrive. POS integration is not required to use the platform -- many restaurants operate perfectly well using just the Admin Portal. But for restaurants that want a deeper integration, the POS connection offers several benefits.

When connected, your POS system can push orders directly into Arrive's tracking engine. This is useful if you take orders through your own system (phone orders, walk-ins) and want them to benefit from Arrive's capacity management. Your POS can also pull the current Arrive menu, synchronize menu updates, and receive real-time status changes via webhooks.

POS systems authenticate with Arrive using API keys rather than user accounts. Each API key is scoped to your restaurant and carries specific permissions (for example, the ability to create orders, read orders, or sync menus). The keys are stored securely -- Arrive never stores the raw key, only a cryptographic hash. Up to five POS connections can be configured per restaurant.

Setting up a POS connection is done through the Admin Portal's POS Settings panel. You select your POS provider, provide a webhook URL where Arrive should send order events, and configure a webhook secret for signature verification. The setup process generates an API key that your POS system uses to communicate with Arrive's API.

POS integration is entirely optional. If you do not use a POS system, or if you prefer to manage orders solely through the Admin Portal, you can skip this entirely and lose nothing.


## The Admin Portal

The Admin Portal is your day-to-day tool for managing your restaurant on Arrive. It is a web application that you access through your browser -- no software to install.

When you sign in, you will see your restaurant's dashboard with a Kanban-style board showing all active orders organized by status. The board has lanes for Incoming (orders just dispatched to your kitchen), In Progress (orders being prepared), Ready (food done, waiting for customer), Fulfilling (customer is picking up), and Completed (finished orders). Orders flow from left to right as your team processes them.

Beyond the order board, the Admin Portal gives you access to menu management (import menus from CSV/Excel, view current menu items, see categories and prices), capacity settings (adjust concurrent order limits and time windows), restaurant images (upload and manage photos of your restaurant), POS settings (configure POS connections if applicable), and archived orders (view completed orders that have rolled off the main board).

A separate guide provides detailed instructions for every feature in the Admin Portal. Your team should review that guide before going live on the platform.


## Going Live

The onboarding process follows these steps. First, an Arrive administrator creates your restaurant on the platform with your name, address, and initial configuration. Second, a restaurant_admin account is created for your designated manager and linked to your restaurant. Third, your manager signs in to the Admin Portal, uploads your menu, adjusts capacity settings if needed, and optionally configures POS integration. Fourth, your restaurant goes live and becomes visible to customers in the Arrive app.

Before going live, we recommend a brief testing period where your team places a few test orders to get familiar with the dashboard, practices moving orders through the status flow, and verifies that the menu looks correct and prices are accurate. This ensures your team is comfortable with the system before real customer orders start coming in.


## Support and Next Steps

If you have questions during onboarding or after going live, the Arrive team is available to help. Common topics include adjusting capacity settings to match your kitchen's throughput, re-importing or updating your menu, troubleshooting POS integration, and understanding the order flow and status transitions.

As the platform evolves, new features will become available to restaurants, including analytics dashboards with insights into order volumes and preparation times, push notifications for new orders (complementing the current audio alerts), adaptive capacity that learns from your kitchen's historical patterns, and kitchen display system integration for in-kitchen order screens.

Arrive is designed to make restaurant pickup better for everyone -- your kitchen staff, your customers, and your bottom line. Welcome aboard.
