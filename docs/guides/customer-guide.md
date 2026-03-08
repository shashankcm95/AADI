# Customer Guide

## Welcome to Arrive

Arrive is a dine-in restaurant ordering app designed around one simple idea: you should be able to order from your table without waiting for a server. No flagging anyone down, no waiting to be noticed, no wondering when your food will come.

Here is how it works. You arrive at a restaurant, sit down at your table, and open the Arrive app or website on your phone. You browse the menu, pick what you want to eat, and place your order. The platform confirms you are at the restaurant, checks the kitchen's current capacity, and dispatches your order at the right time. Your food is prepared fresh and brought to your table.

This guide walks you through everything you need to know as an Arrive customer, from creating your account to ordering your first meal.


## Getting Started

### Creating Your Account

To use Arrive, you need to create an account. You can do this on the web at the Arrive website or through the Arrive mobile app on your iPhone.

When you sign up, you will be asked for your email address and a password. That is all you need to get started. Your email address becomes your login, and you will use it to sign in each time you open the app.

After you create your account, you can optionally set up your profile with your name and a profile picture. Your name is what the restaurant will see on your order, so it helps them identify who to serve. If you do not set a name, your orders will show up as "Guest."

### Signing In

Each time you open the Arrive app or website, you will be asked to sign in with your email and password. The app remembers your session, so you will not need to sign in every time -- only when your session has expired or you have explicitly signed out.


## Browsing Restaurants and Menus

Once you are signed in, you will see a list of restaurants available near you. Each restaurant displays its name, a description, and images of the establishment if the restaurant has uploaded them.

You can browse the full list of restaurants or mark your favorites for quick access later. To favorite a restaurant, look for the heart or star icon on the restaurant listing and tap it. Your favorites are saved to your account and appear in a dedicated Favorites section, making it easy to reorder from places you love.

When you tap on a restaurant, you will see its full menu organized by category. Each menu item shows the item name, a description (if the restaurant has provided one), its category (like Appetizers, Entrees, Drinks, and so on), and the price. Browse through the categories to find what you want, and add items to your cart by tapping the add button next to each item.


## Placing an Order

### Building Your Cart

As you browse a restaurant's menu, you can add items to your cart. Each item you add shows up in your cart with the quantity and price. You can adjust quantities or remove items before you finalize your order.

There is a maximum quantity of 99 for any single item on an order. If you need more than that, you are probably catering, and you should contact the restaurant directly.

### Reviewing and Confirming

When you are happy with your selections, open your cart to review everything. You will see each item, its quantity, and the price. The cart also shows your order total.

When you are ready, tap the Place Order button to confirm. The button is designed to prevent accidental double-taps -- once you tap it, it disables itself while your order is being submitted, so you will not accidentally place duplicate orders.

### Payment

Arrive currently uses a pay-at-restaurant model. This means you do not enter a credit card or pay through the app. Instead, you pay for your meal at the restaurant, just as you would for any dine-in order. Your server will bring the check to your table when you are ready, and the restaurant handles payment using their existing payment system.

Your order in Arrive shows the total so you know what to expect, but the actual transaction happens at the restaurant.


## Understanding Order Status

After you place your order, you can track its progress in real time. Here is what each status means in plain language.

### Pending

Your order has been placed and confirmed. It is in the queue and will be dispatched to the kitchen based on the restaurant's current capacity. If the platform is still confirming your presence at the restaurant, your order will stay in this state briefly.

### Waiting for Capacity

The restaurant's kitchen is busy right now, and your order is in a short queue. This happens when a restaurant has reached its maximum number of concurrent orders for the current time window. Your order will be sent to the kitchen as soon as a slot opens up. This is usually a matter of minutes.

### Sent to Restaurant

Your order has been dispatched to the restaurant's kitchen. The kitchen has received your order and knows what to prepare. Your food is about to be made.

### In Progress

The kitchen is actively preparing your food. Sit tight -- your meal is on its way.

### Ready

Your food is prepared and will be brought to your table shortly. The restaurant staff can see your name on the order.

### Fulfilling

The restaurant is serving your food to your table. This status means your order is being delivered to you.

### Completed

All done. You have received your food at your table, and the order is closed. If you finish your meal and leave the restaurant, the app may automatically mark your order as completed for convenience.

### Canceled

You or the system canceled the order. Orders can be canceled while they are in the Pending or Waiting for Capacity state. Once the order has been sent to the kitchen, it can no longer be canceled through the app -- you would need to speak with the restaurant directly.


## How Presence Detection Works

This is what makes Arrive different from other ordering apps. Here is how the platform confirms you are at the restaurant and coordinates the ordering flow.

### Location Tracking

When you use the Arrive mobile app, it asks for permission to access your location. This is entirely optional on the web, but on the mobile app, location tracking is what powers the core dine-in experience.

The app does not track you all the time. It monitors your location only when you have an active dine-in order, to confirm you are at the restaurant. Once your order is completed or canceled, location tracking stops.

### Arriving at the Restaurant

As you approach or enter the restaurant, the app detects your proximity through geofence zones. When you are seated inside and place your order, the platform confirms your presence automatically. If you are already inside the restaurant (the typical dine-in scenario), the app detects this immediately and dispatches your order to the kitchen, subject to capacity availability.

### Progressive Proximity Signals

The platform uses three proximity zones around each restaurant:

**Five Minutes Out** -- roughly 1,500 meters away. This is an early signal that you are heading toward the restaurant.

**Parking** -- about 150 meters away, meaning you are in the immediate vicinity. The restaurant sees an update that you are nearby.

**At the Door** -- within about 30 meters. You are inside or right at the entrance. For dine-in orders placed from your table, this is the signal that triggers dispatch.

### Leaving

After you have finished your meal and leave the restaurant, the app detects your departure. If your order is in the Fulfilling state (meaning the restaurant has marked your food as served), the app automatically completes the order. This saves you and the restaurant the trouble of manually closing it out.


## Managing Your Profile

You can update your profile at any time through the app. Your profile includes your display name (this is what restaurants see on your orders) and a profile picture.

To update your name, go to the Profile section, edit the name field, and save. To update your profile picture, tap on your avatar or the photo upload area and select a new image. The app uploads your photo securely, and it will appear on your profile going forward.

If you make changes and decide you do not want to keep them, you can cancel before saving and your original information will be restored.


## Frequently Asked Questions

### Do I need the mobile app, or can I use the website?

You can use either. The website lets you browse restaurants, place orders, track their status, and manage your profile. The mobile app does all of that plus automatic location detection, which is what enables seamless presence confirmation at the restaurant. If you use only the website, you can still place dine-in orders -- the restaurant will receive them, though the automatic presence confirmation will not be available.

### How does Arrive know I am at the restaurant?

The mobile app uses your phone's GPS to detect when you are within the restaurant's geofence zones. There are three zones at different distances. You must grant location permission for this to work, and the app only uses your location when you have an active order.

### Can I cancel my order?

Yes, as long as the order has not been sent to the kitchen yet. If your order is still in the Pending or Waiting for Capacity state, you can cancel it through the app. Once the order has been dispatched to the restaurant and they have started preparing it, cancellation is no longer available through the app. In that case, you would need to speak with your server or the restaurant staff directly.

### Why is my order "Waiting for Capacity"?

The restaurant has a limit on how many orders they can handle at the same time. Your order is in a short queue and will be sent to the kitchen as soon as a slot opens up. This is usually just a few minutes and it is the system working as designed -- it prevents the kitchen from being overwhelmed, which means better food quality for everyone.

### Do I pay through the app?

Not currently. Arrive uses a pay-at-restaurant model. You pay for your meal at the table when you are ready, using whatever payment method the restaurant accepts. The app shows you the order total so there are no surprises.

### What if the app is not detecting my location at the restaurant?

Make sure location services are enabled on your phone and that you have granted the Arrive app permission to access your location. GPS signal can sometimes be weak inside buildings. If automatic detection is not working, your order will still be received by the restaurant -- the platform handles this gracefully.

### Can I reorder from a previous restaurant?

Yes. Use the Favorites feature to mark restaurants you like. They will appear in your Favorites section for quick access. From there, you can browse their menu and place a new order.

### How do I sign out?

Look for the Sign Out button in the app, typically in the profile or settings area. Signing out clears your session. You will need to sign in again the next time you open the app.

### Something went wrong with my order. What do I do?

If your order is not showing the correct status, try refreshing the order list. If the issue persists, the best course of action is to speak with the restaurant staff directly. They can see your order on their dashboard and can update its status or help resolve any issues.
