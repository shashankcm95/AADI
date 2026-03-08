# Admin Portal Guide

## Logging In

The Admin Portal is a web application that you access through your browser. Navigate to the Admin Portal URL provided during your restaurant's onboarding. You will be presented with a sign-in screen powered by AWS Cognito.

Enter the email address and password associated with your restaurant administrator account. These credentials were set up during onboarding, and they are specific to the Admin Portal -- they are separate from any customer account you might have.

When you sign in, the system checks your user role. If your account has the "restaurant_admin" role, you will be taken directly to your restaurant's dashboard. Your account is linked to a specific restaurant, so you will only see orders and settings for your assigned location. If your account has the "admin" (super admin) role, you will see a broader administrative dashboard with the ability to manage multiple restaurants and invite new restaurant administrators.

If you attempt to sign in with a customer account, access will be denied. The Admin Portal is restricted to restaurant_admin and admin roles only.

Once signed in, your session persists until it expires or you explicitly sign out. The sign-out button is located in the top-right corner of the header, next to your username.


## Dashboard Overview

After signing in, you land on the main dashboard. This is the command center for your restaurant's operations on Arrive.

The dashboard is organized around a Kanban-style order board that shows all active orders in real-time. The board updates automatically every five seconds through background polling, so you do not need to manually refresh to see new orders.

At the top of the dashboard, you will see a header bar with your restaurant's name (or "AADI Restaurant Portal" if no name is set), your username, and a sign-out button. Below the header, a stats bar displays three key counts at a glance: the number of orders in the Incoming lane (recently dispatched), the number of active orders being prepared, and the number of pending orders not yet dispatched.

Below the stats bar, a toolbar row provides a manual refresh button (for those times you want an immediate update rather than waiting for the next polling cycle) and a timestamp showing when the data was last refreshed.

If your restaurant is currently marked as inactive, a yellow warning banner appears at the top of the page informing you that customers cannot see your restaurant. An "Activate Now" button is available directly in the banner to make your restaurant visible again.


## The Order Board

The order board is the heart of the Admin Portal. It displays all active orders as cards organized into status lanes, flowing from left to right as orders progress through the fulfillment process.

### Incoming Lane

Orders that have been dispatched to your restaurant appear here. These are orders where the customer is approaching and the platform has sent the order to your kitchen. Each order card shows the order ID (a short hash for easy reference), the customer's name, the items they ordered with quantities, and the order's arrival status (whether the customer is five minutes out, parking, or at the door).

When a new order arrives in this lane, the dashboard plays a short audio notification tone and briefly flashes the page background to get your attention. This ensures your team notices new orders even if they are not actively watching the screen.

Orders that sit in the Incoming lane for more than two minutes are automatically promoted to In Progress. This auto-promotion is a safety net that ensures no order gets lost even if the kitchen misses the notification. The two-minute delay gives the team time to manually acknowledge and advance the order before the system does it automatically.

### In Progress Lane

Orders in this lane are being actively prepared by the kitchen. To move an order here from Incoming, your team advances the order status through the order card's action button. Once in this lane, the kitchen should be working on the order.

### Ready Lane

When the food is done, move the order to Ready. This signals that preparation is complete and the order is waiting for the customer to arrive and be served.

### Fulfilling Lane

When the customer has arrived and you are serving their food to the table, move it to Fulfilling. This status represents the handoff moment -- the customer is seated and receiving their meal.

### Completed Lane

Finished orders move here. The board shows the most recent 20 completed orders. Older completed orders roll into the Archived section, accessible from the toolbar tabs.

Each order card on the board also offers a "Complete" action that advances the order through all remaining steps in a single click. For example, if an order is In Progress and you want to close it out quickly (perhaps you are serving the food immediately), the Complete action will move it through Ready, Fulfilling, and Completed in sequence. This is a time-saver during busy periods.

### Order Card Details

Each order card on the board displays the order number (last six characters of the order ID for easy verbal reference), the customer's name, a summary of all items with quantities (for example, "Margherita Pizza x2, Caesar Salad x1"), and the arrival status when available. Timestamps are displayed in your local time format, showing when the order was created and last updated.


## Menu Management

The Admin Portal provides full menu management capabilities. To access menu management, click the "Manage Menu" tab in the toolbar area below the restaurant picker.

### Viewing Your Current Menu

When you open the menu management panel, the portal loads and displays your restaurant's current menu. Items are shown in a table sorted by category and then by name, with columns for Category, Name, Price, and Description. This gives you a quick overview of everything currently available to customers.

If your menu is empty (for example, when you are first setting up), the panel will show a message indicating that no items were found and prompting you to import a menu.

### Importing a Menu

The primary way to populate or update your menu is through file import. The Menu Ingestion panel accepts CSV, XLSX, and XLS files. Your file should have columns for Category, Name, Description, and Price.

To import a menu, click the file upload area and select your spreadsheet file. The system parses the file immediately and shows a preview of the first five items, including the category, name, and price for each row. Review the preview to confirm the data looks correct.

When you are satisfied with the preview, click the "Import" button. The system will ask you to confirm because importing overwrites your existing menu. Once confirmed, the system processes all rows in the file. Items that are valid (they have a name and a valid price) are imported successfully. Items with issues -- such as a missing name or an unparseable price -- are skipped and reported in the result summary so you know exactly which rows were not imported and why.

Prices are handled carefully during import. The system strips dollar signs and commas from price strings, converts to a Decimal value, and calculates an integer price_cents value using banker's rounding (ROUND_HALF_UP). This means a price of $9.995 rounds to $10.00, and $9.994 rounds to $9.99. Each item is also assigned a unique identifier if it does not already have one.

After a successful import, the menu display refreshes automatically to show your updated items.

### Menu Item Fields

Each menu item in the system carries several fields. The Name is the display name customers see. The Category groups items together (Appetizers, Entrees, Drinks, Desserts, or whatever categories your restaurant uses). The Description is optional additional text about the item. The Price is the dollar amount displayed to customers. The Price Cents is the integer representation used internally for calculations (for example, $12.99 is stored as 1299 cents). The ID is a unique identifier assigned automatically if not provided.


## Restaurant Settings

While the Admin Portal does not have a standalone "Settings" page separate from the dashboard, several configuration aspects of your restaurant are managed through the toolbar tabs.

### Restaurant Information

If you have the ability to add or edit restaurants (super admin role), the "Add Restaurant" button in the restaurant picker area opens a form for creating a new restaurant entry. For restaurant admins who are assigned to a specific restaurant, the restaurant name and ID are displayed in the picker area but are not editable from the portal -- changes to core restaurant information (name, address) are managed by Arrive platform administrators.

### Restaurant Images

Click the "Images" tab in the toolbar to open the Restaurant Image Manager. This panel allows you to upload, view, and manage photographs of your restaurant that appear on your listing in the customer app.

Images are uploaded to S3 via presigned URLs, meaning the upload goes directly from your browser to secure cloud storage without passing through any intermediate server. You can upload multiple images, reorder them, and remove images you no longer want to display. After making changes, save the updated image list. The customer-facing listing updates to reflect your changes.

### Activating and Deactivating

If your restaurant is inactive (not visible to customers), the yellow warning banner at the top of the dashboard provides an "Activate Now" button. Clicking this button makes your restaurant immediately visible in the customer app. The activation happens through an API call that updates your restaurant's active status.

The system also includes auto-activation logic: when a restaurant_admin signs in and their assigned restaurant is inactive, the portal automatically activates it. This prevents situations where a restaurant is accidentally left in an inactive state.


## Capacity Configuration

Click the "Capacity" tab in the toolbar to open the Capacity Settings modal. This is where you control how the platform manages order flow to your kitchen.

### Max Concurrent Orders

This setting determines the maximum number of orders that can be actively dispatched within a single time window. The default is 10. If you find your kitchen is overwhelmed during peak times, lower this number. If you have kitchen capacity to spare, raise it. The system enforces this limit atomically -- when the limit is reached, new orders queue in a "Waiting for Capacity" state rather than flooding the kitchen.

### Window Size

The time window determines how capacity is measured. The default is 5 minutes (300 seconds). You can choose from 5, 10, 15, or 30-minute windows. A shorter window provides tighter control but means capacity resets more frequently. A longer window smooths out the flow but allows larger bursts within a single period.

For most restaurants, the 5-minute default works well. If your kitchen has consistent throughput and you want to avoid brief bursts, a 10 or 15-minute window might be preferable.

### Dispatch Trigger Zone

This setting controls which geofence zone triggers order dispatch. There are three options:

Zone 1 (default, approximately 1,500 meters) corresponds to the "5 Minutes Out" arrival event. This gives the kitchen the most preparation lead time and is suitable for restaurants with standard preparation times.

Zone 2 (approximately 150 meters) corresponds to "Parking." This is a shorter lead time, suitable for restaurants with faster preparation -- think sandwich shops, salad bars, or pizza places with pre-made items.

Zone 3 (approximately 30 meters) corresponds to "At Door." This is the shortest lead time and is appropriate for very fast preparation -- coffee shops, juice bars, or establishments where the order can be assembled in under two minutes.

The zone distances are managed by the Arrive platform team and cannot be changed by individual restaurants. However, you choose which zone triggers your orders, allowing you to match the dispatch timing to your kitchen's actual preparation speed.

After adjusting any of these settings, click "Save Changes." The modal closes after a successful save, and the new settings take effect immediately for all subsequent orders.


## POS Settings

Click the "POS" tab in the toolbar to open the POS Integrations panel. This is where you manage connections between Arrive and your point-of-sale system.

### Enabling POS Integration

The POS panel has a global enable/disable toggle at the top. When POS integration is disabled, no POS connections are active even if they are configured. Toggle this on when you are ready to start using POS integration.

### Managing Connections

The panel shows all configured POS connections as cards, each displaying the connection label, provider icon, webhook URL, and webhook secret (partially masked for security). Each connection has its own enable/disable toggle and a remove button.

To add a new POS connection, click the "Add POS Connection" button. A form appears asking for:

The Provider, which is the type of POS system you are connecting. The portal supports Square, Toast, Clover, and Custom as provider types. Selecting the right provider ensures that order data is mapped correctly between Arrive's format and your POS system's format.

The Label, which is a friendly name for this connection (for example, "Square - Main Register" or "Toast - Dine In"). This helps you distinguish between connections if you have more than one.

The Webhook URL, which is the HTTPS endpoint where Arrive sends order events to your POS system. This must be an HTTPS URL -- plain HTTP is not accepted for security reasons.

The Webhook Secret, which is used for HMAC-SHA256 signature verification. Your POS system uses this secret to verify that incoming webhooks genuinely came from Arrive and were not tampered with in transit.

After filling in the form, click "Add Connection." The connection is saved immediately. You can add up to five POS connections per restaurant.

### API Key Authentication

POS systems authenticate with Arrive's API using API keys rather than username and password. Each API key is scoped to your restaurant and carries a set of permissions that control what the POS system can do. Common permissions include orders:read (view orders), orders:write (create orders and update status), menu:read (fetch your Arrive menu), and menu:write (push menu updates from the POS).

API keys are stored securely. Arrive never stores the raw key -- only a SHA-256 cryptographic hash. This means that even in the unlikely event of a data breach, the actual API keys cannot be recovered from the stored data. Keys can also be set to expire after a configurable period.

### Menu Synchronization

If POS menu sync is enabled for your restaurant, your POS system can push menu updates to Arrive through the API. This is useful if your POS is the source of truth for your menu and you want changes made there to automatically appear in the Arrive customer app. Note that menu sync from POS replaces the existing Arrive menu, so it should be treated as a one-way sync from POS to Arrive.

If you prefer to manage your menu through the Admin Portal's CSV/Excel import, you can leave POS menu sync disabled and use the POS connection solely for order management.


## Image Uploads

The "Images" tab opens the Restaurant Image Manager. This tool allows you to manage the photos that appear on your restaurant's listing in the customer-facing app.

Images are stored in S3 (Amazon's cloud storage service) and delivered through CloudFront (Amazon's content delivery network) for fast loading. When you upload an image, the portal requests a presigned upload URL from the backend, which allows your browser to upload the file directly to S3 securely. This means uploads are fast and do not go through any intermediate server.

You can upload multiple images. The first image typically serves as the primary photo shown on the restaurant card in the customer app, and additional images appear when customers view your restaurant's detail page. You can reorder images by adjusting their position and remove images you no longer want displayed.

After making changes, click the save button to persist the updated image list. The changes take effect immediately -- customers will see the updated photos the next time they browse your restaurant.


## User Management (Admin Role)

If your account has the "admin" (super admin) role, you see a different dashboard than restaurant administrators. The Admin Dashboard provides platform-wide management capabilities.

Super admins can view and manage all restaurants on the platform, not just a single assigned location. The restaurant picker shows all registered restaurants, and the admin can switch between them to view orders and manage settings for any location.

Super admins can also add new restaurants to the platform through the "Add Restaurant" button, which opens a form for entering the restaurant's name, address, and initial configuration. After creating a restaurant, the admin can assign a restaurant_admin user to manage it by updating the user's Cognito attributes.

The Admin Dashboard separates these platform-wide functions from the restaurant-specific dashboard that restaurant admins see, ensuring that each user role sees only the tools and data relevant to their responsibilities.


## Common Tasks and Workflows

### Starting Your Day

When you begin your shift, sign in to the Admin Portal. If your restaurant is inactive, the system will automatically activate it (or you can click the "Activate Now" button in the warning banner). The order board begins polling immediately, and any pending or active orders will appear on the Kanban board. Make sure your browser tab stays open so you can hear audio notifications for incoming orders.

### Processing an Incoming Order

When a new order arrives, you will hear an audio tone and see the page flash briefly. The order appears in the Incoming lane. Review the items on the order card. When the kitchen is ready to start working on it, advance the order to "In Progress." If you do not advance it within two minutes, the system does so automatically to prevent orders from being missed.

### Completing an Order

As the kitchen finishes each order, advance it through the statuses: In Progress to Ready when the food is done, Ready to Fulfilling when the customer has arrived and you are serving them, and Fulfilling to Completed when the handoff is finished. Alternatively, use the Complete button to jump through all remaining steps at once.

If the customer's mobile app detects that they have left the vicinity after their order was marked as Fulfilling, the platform automatically marks the order as Completed. This means you may not need to manually complete every order -- many will close themselves.

### Updating Your Menu

When your menu changes -- new items, removed items, price changes -- go to the Manage Menu tab. Prepare an updated CSV or Excel file with your full menu (all items, not just the changes, since import replaces the existing menu). Upload the file, review the preview, and confirm the import. The updated menu is immediately available to customers.

### Adjusting Capacity During Busy Periods

If the kitchen is overwhelmed during a rush, open the Capacity settings and temporarily lower the max concurrent orders. This causes the platform to queue more orders rather than flooding the kitchen. When the rush subsides, raise the limit back to your normal level. Changes take effect immediately for all new orders.

### Checking Archived Orders

Completed orders beyond the most recent 20 are moved to the archive. Click the "Archived" tab in the toolbar to view a table of all archived orders with their order number, customer name, completion time, and items summary. This is useful for end-of-day reconciliation or for looking up a specific past order.

### Ending Your Day

When you are done for the day, you can simply sign out. If you want to prevent new orders from being dispatched while you are closed, you can deactivate your restaurant (if this option is available through your admin), which removes it from the customer-facing app. The platform does not currently have automated operating hours, so activation and deactivation are manual operations.
