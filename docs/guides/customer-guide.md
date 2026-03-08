# Customer Guide

## Welcome to Arrive

Arrive is a restaurant pickup app designed around one simple idea: your food should be ready exactly when you walk through the door. Not ten minutes before, sitting under a heat lamp getting cold. Not ten minutes after, leaving you standing around waiting. Exactly when you arrive.

Here is how it works. You browse restaurants, pick what you want to eat, and place your order. Then you go about your day. When you are ready to head to the restaurant, Arrive tracks your approach (with your permission) and tells the kitchen to start cooking at just the right moment. By the time you park and walk in, your food is freshly made and waiting for you.

This guide walks you through everything you need to know as an Arrive customer, from creating your account to picking up your first order.


## Getting Started

### Creating Your Account

To use Arrive, you need to create an account. You can do this on the web at the Arrive website or through the Arrive mobile app on your iPhone.

When you sign up, you will be asked for your email address and a password. That is all you need to get started. Your email address becomes your login, and you will use it to sign in each time you open the app.

After you create your account, you can optionally set up your profile with your name and a profile picture. Your name is what the restaurant will see on your order, so it helps them know who to call when your food is ready. If you do not set a name, your orders will show up as "Guest."

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

Arrive currently uses a pay-at-restaurant model. This means you do not enter a credit card or pay through the app. Instead, you pay for your food when you arrive at the restaurant, just as you would for any walk-in order. The restaurant handles payment at their counter using their existing payment system.

Your order in Arrive shows the total so you know what to expect, but the actual transaction happens face-to-face at the restaurant.


## Understanding Order Status

After you place your order, you can track its progress in real time. Here is what each status means in plain language.

### Pending

Your order has been placed and confirmed. The restaurant has not started working on it yet. This is normal and expected -- Arrive holds your order until you are heading to the restaurant, so the food is cooked fresh when you arrive rather than sitting around.

### Waiting for Capacity

The restaurant is busy right now, and your order is in a short queue. This happens when a restaurant has reached its maximum number of concurrent orders for the current time window. Your order will be sent to the kitchen as soon as a slot opens up. This is usually a matter of minutes.

### Sent to Restaurant

Your order has been dispatched to the restaurant's kitchen. This typically happens when the app detects that you are approaching the restaurant -- about five minutes away. The kitchen has received your order and knows what to prepare.

### In Progress

The kitchen is actively preparing your food. This is the status you want to see when you are getting close to the restaurant.

### Ready

Your food is done and waiting for you to pick it up. Head inside and let them know your name. The restaurant staff can see your name on the order.

### Fulfilling

You have arrived and the restaurant is handing you your order. This status means you are at the restaurant and the pickup is in progress.

### Completed

All done. You have your food, you are on your way, and the order is closed. If you were near the restaurant and you leave the vicinity, the app may automatically mark your order as completed for convenience.

### Canceled

You or the system canceled the order. Orders can be canceled while they are in the Pending or Waiting for Capacity state. Once the order has been sent to the kitchen, it can no longer be canceled through the app -- you would need to speak with the restaurant directly.


## The Arrival Flow

This is what makes Arrive different from other ordering apps. Here is what happens behind the scenes as you head to pick up your food.

### How Location Tracking Works

When you use the Arrive mobile app, it asks for permission to access your location. This is entirely optional on the web, but on the mobile app, location tracking is what powers the core timing feature.

The app does not track you all the time. It monitors your location only when you have an active order that is pending pickup. Once your order is completed or canceled, location tracking stops.

### Five Minutes Away

When the app detects that you are about five minutes from the restaurant (roughly 1,500 meters away, depending on the restaurant's configuration), it sends a signal to the platform. If the restaurant has capacity available, this is when your order gets dispatched to the kitchen. The kitchen starts cooking, timed to have your food ready right as you walk in.

### Parking

When you are very close to the restaurant -- within about 150 meters, which usually means you are pulling into the parking lot -- the app sends another signal. If your order had not already been dispatched (for example, if the restaurant was at capacity when you were five minutes away), this signal can trigger dispatch. The restaurant also sees an update that you are nearby.

### At the Door

When you are within about 30 meters of the restaurant, the app sends a final proximity signal. The restaurant knows you are right outside or walking in. For most orders, your food should be ready or nearly ready at this point.

### Leaving

After you have picked up your food and you leave the restaurant's vicinity, the app detects your departure. If your order is in the Fulfilling state (meaning the restaurant has marked it as being handed to you), the app automatically completes the order. This saves you and the restaurant the trouble of manually closing it out.


## Managing Your Profile

You can update your profile at any time through the app. Your profile includes your display name (this is what restaurants see on your orders) and a profile picture.

To update your name, go to the Profile section, edit the name field, and save. To update your profile picture, tap on your avatar or the photo upload area and select a new image. The app uploads your photo securely, and it will appear on your profile going forward.

If you make changes and decide you do not want to keep them, you can cancel before saving and your original information will be restored.


## Frequently Asked Questions

### Do I need the mobile app, or can I use the website?

You can use either. The website lets you browse restaurants, place orders, track their status, and manage your profile. The mobile app does all of that plus location tracking, which is what enables the "food ready when you arrive" feature. If you use only the website, you can still place orders -- the restaurant will just receive them without the arrival timing optimization.

### How does Arrive know when I am near the restaurant?

The mobile app uses your phone's GPS to detect when you cross into zones around the restaurant. There are three zones at different distances. You must grant location permission for this to work, and the app only uses your location when you have an active order.

### Can I cancel my order?

Yes, as long as the order has not been sent to the kitchen yet. If your order is still in the Pending or Waiting for Capacity state, you can cancel it through the app. Once the order has been dispatched to the restaurant and they have started preparing it, cancellation is no longer available through the app. In that case, you would need to contact the restaurant directly.

### Why is my order "Waiting for Capacity"?

The restaurant has a limit on how many orders they can handle at the same time. Your order is in a short queue and will be sent to the kitchen as soon as a slot opens up. This is usually just a few minutes and it is the system working as designed -- it prevents the kitchen from being overwhelmed, which means better food quality for everyone.

### Do I pay through the app?

Not currently. Arrive uses a pay-at-restaurant model. You pay for your food at the restaurant's counter when you pick it up, using whatever payment method the restaurant accepts. The app shows you the order total so there are no surprises.

### What if I placed an order but I am not heading to the restaurant yet?

That is perfectly fine. Your order stays in the Pending state until you start heading to the restaurant. The kitchen will not start cooking until the app detects that you are approaching. Orders do eventually expire if left in the Pending state for too long (typically one hour), so do not wait all day. But there is no rush -- the whole point of Arrive is that the timing is based on your arrival, not on when you placed the order.

### Can I reorder from a previous restaurant?

Yes. Use the Favorites feature to mark restaurants you like. They will appear in your Favorites section for quick access. From there, you can browse their menu and place a new order.

### How do I sign out?

Look for the Sign Out button in the app, typically in the profile or settings area. Signing out clears your session. You will need to sign in again the next time you open the app.

### Something went wrong with my order. What do I do?

If your order is not showing the correct status, try refreshing the order list. If the issue persists, the best course of action is to contact the restaurant directly. They can see your order on their dashboard and can update its status or help resolve any issues.
