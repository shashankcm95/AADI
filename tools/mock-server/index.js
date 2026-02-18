/**
 * Arrive Demo Mock Server
 * 
 * A simple in-memory server that simulates the backend API for demo purposes.
 * Both Client (5173) and Admin (5174) apps will call this server to share order data.
 * 
 * Run with: node mock-server.js
 * 
 * Endpoints:
 * - GET /v1/orders - List all orders
 * - POST /v1/orders - Create order
 * - POST /v1/orders/:id/vicinity - Simulate vicinity trigger
 * - GET /v1/restaurants/:id/orders - Get orders for restaurant
 * - POST /v1/restaurants/:id/orders/:orderId/status - Update order status
 */

const http = require('http');
const fs = require('fs');
const path = require('path');

// Load Seed Data
const SEED_FILE = path.join(__dirname, 'data', 'seed_restaurants.json');
let RESTAURANTS = [];

try {
    RESTAURANTS = JSON.parse(fs.readFileSync(SEED_FILE, 'utf8'));
    console.log(`✅ Loaded ${RESTAURANTS.length} restaurants from seed file.`);
} catch (e) {
    console.error('❌ Failed to load seed file:', e);
}

// In-Memory Order Store
let orders = [];

const PORT = 3001;

const server = http.createServer((req, res) => {
    // CORS Headers - Allow both frontend origins
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');

    if (req.method === 'OPTIONS') {
        res.writeHead(204);
        res.end();
        return;
    }

    const url = new URL(req.url, `http://localhost:${PORT}`);
    const pathname = url.pathname;
    const method = req.method;

    let body = '';
    req.on('data', chunk => body += chunk);
    req.on('end', () => {
        const payload = body ? JSON.parse(body) : {};

        // Route: GET /v1/restaurants
        if (method === 'GET' && pathname === '/v1/restaurants') {
            const publicRestaurants = RESTAURANTS.map(({ pin, ...r }) => r); // Exclude PINs
            json(res, 200, { restaurants: publicRestaurants });
            return;
        }

        // Route: GET /v1/restaurants/:id/menu
        if (method === 'GET' && pathname.match(/^\/v1\/restaurants\/[^/]+\/menu$/)) {
            const restaurantId = pathname.split('/')[3];
            const restaurant = RESTAURANTS.find(r => r.restaurant_id === restaurantId);
            if (restaurant) {
                json(res, 200, { menu: { items: restaurant.menu || [] } });
            } else {
                json(res, 404, { error: 'Restaurant not found' });
            }
            return;
        }

        // Route: POST /v1/auth/staff-login
        if (method === 'POST' && pathname === '/v1/auth/staff-login') {
            const { pin } = payload;
            const restaurant = RESTAURANTS.find(r => r.pin === pin);

            if (restaurant) {
                // Return everything except PIN
                const { pin: _, ...rest } = restaurant;
                json(res, 200, {
                    success: true,
                    token: `mock_token_${restaurant.restaurant_id}`,
                    restaurant: rest
                });
            } else {
                json(res, 401, { error: 'Invalid PIN' });
            }
            return;
        }

        // Route: POST /v1/orders
        if (method === 'POST' && pathname === '/v1/orders') {
            const order = {
                order_id: `ord_demo_${Date.now()}`,
                restaurant_id: payload.restaurant_id,
                status: 'PENDING_NOT_SENT',
                created_at: Date.now(),
                customer_name: payload.customer_name || 'Guest',
                items: payload.items || [],
                total_cents: payload.items?.reduce((sum, i) => sum + (i.price_cents || 0) * (i.qty || 1), 0) || 0,
                receipt_mode: 'SOFT',
                vicinity: false
            };
            orders.push(order);
            console.log(`✅ Order Created: ${order.order_id}`);
            json(res, 201, { order_id: order.order_id, status: order.status });
            return;
        }

        // Route: GET /v1/orders/:id
        if (method === 'GET' && pathname.match(/^\/v1\/orders\/[^/]+$/)) {
            const orderId = pathname.split('/')[3];
            const order = orders.find(o => o.order_id === orderId);
            if (order) {
                json(res, 200, order);
            } else {
                json(res, 404, { error: 'Not found' });
            }
            return;
        }

        // Route: POST /v1/orders/:id/vicinity
        if (method === 'POST' && pathname.match(/^\/v1\/orders\/[^/]+\/vicinity$/)) {
            const orderId = pathname.split('/')[3];
            const order = orders.find(o => o.order_id === orderId);
            if (order && payload.vicinity === true) {
                order.vicinity = true;
                order.status = 'SENT_TO_DESTINATION';
                order.sent_at = Date.now();
                console.log(`🔔 Order Sent to Kitchen: ${orderId}`);
            }
            json(res, 200, { order_id: orderId, status: order?.status });
            return;
        }

        // Route: GET /v1/restaurants/:id/orders
        if (method === 'GET' && pathname.match(/^\/v1\/restaurants\/[^/]+\/orders$/)) {
            const restaurantId = pathname.split('/')[3];
            const status = url.searchParams.get('status');
            let filtered = orders.filter(o => o.restaurant_id === restaurantId);
            if (status && status !== 'all') {
                filtered = filtered.filter(o => o.status === status);
            }
            json(res, 200, { orders: filtered });
            return;
        }

        // Route: POST /v1/restaurants/:id/orders/:orderId/status
        if (method === 'POST' && pathname.match(/^\/v1\/restaurants\/[^/]+\/orders\/[^/]+\/status$/)) {
            const parts = pathname.split('/');
            const orderId = parts[5];
            const order = orders.find(o => o.order_id === orderId);
            if (order) {
                order.status = payload.status;
                console.log(`🔄 Order Status Updated: ${orderId} -> ${payload.status}`);
            }
            json(res, 200, { order_id: orderId, status: payload.status });
            return;
        }

        // Route: POST /v1/restaurants/:id/orders/:orderId/ack
        if (method === 'POST' && pathname.match(/^\/v1\/restaurants\/[^/]+\/orders\/[^/]+\/ack$/)) {
            const parts = pathname.split('/');
            const orderId = parts[5];
            const order = orders.find(o => o.order_id === orderId);
            if (order) {
                order.receipt_mode = 'HARD';
            }
            json(res, 200, { order_id: orderId, receipt_mode: 'HARD' });
            return;
        }

        // Default 404
        json(res, 404, { error: 'Route not found' });
    });
});

// ============================================================
// POS Integration Routes (/v1/pos/*)
// API Key Authentication (X-POS-API-Key header)
// ============================================================

const POS_API_KEYS = {
    'pos_test_key_toast_001': { restaurant_id: 'rest_demo_001', pos_system: 'toast', permissions: ['*'] },
    'pos_test_key_square_001': { restaurant_id: 'rest_demo_002', pos_system: 'square', permissions: ['*'] },
};

function authenticatePosRequest(req) {
    const apiKey = req.headers['x-pos-api-key'];
    if (!apiKey || !POS_API_KEYS[apiKey]) return null;
    return { api_key: apiKey, ...POS_API_KEYS[apiKey] };
}

server.on('request', (req, res) => {
    const { method, url } = req;
    const parsedUrl = new URL(url, `http://${req.headers.host}`);
    const pathname = parsedUrl.pathname;

    // Only handle /v1/pos/* routes
    if (!pathname.startsWith('/v1/pos/')) return;

    // Set CORS headers
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type, X-POS-API-Key');

    if (method === 'OPTIONS') { json(res, 204, ''); return; }

    // Authenticate
    const keyRecord = authenticatePosRequest(req);
    if (!keyRecord) {
        json(res, 401, { error: 'Unauthorized', message: 'Missing or invalid X-POS-API-Key' });
        return;
    }

    let body = '';
    req.on('data', chunk => { body += chunk; });
    req.on('end', () => {
        let payload = {};
        try { payload = body ? JSON.parse(body) : {}; } catch (e) { }

        const restaurantId = keyRecord.restaurant_id;

        // POST /v1/pos/orders — Create order from POS
        if (method === 'POST' && pathname === '/v1/pos/orders') {
            const order = {
                order_id: `ord_pos_${Date.now()}`,
                session_id: `ord_pos_${Date.now()}`,
                destination_id: restaurantId,
                restaurant_id: restaurantId,
                items: payload.items || [],
                status: 'PENDING_NOT_SENT',
                arrival_status: null,
                payment_mode: payload.payment_mode || 'PAY_AT_RESTAURANT',
                pos_order_ref: payload.pos_order_ref || '',
                pos_system: keyRecord.pos_system,
                total_cents: (payload.items || []).reduce((sum, i) => sum + (i.price_cents || 0) * (i.qty || 1), 0),
                arrive_fee_cents: Math.round((payload.items || []).reduce((sum, i) => sum + (i.price_cents || 0) * (i.qty || 1), 0) * 0.02),
                created_at: Math.floor(Date.now() / 1000),
                vicinity: false,
                tip_cents: 0,
            };
            orders.push(order);
            console.log(`✅ [POS] Order Created: ${order.order_id} from ${keyRecord.pos_system}`);
            json(res, 201, { arrive_order_id: order.order_id, pos_order_ref: order.pos_order_ref, status: order.status, arrive_fee_cents: order.arrive_fee_cents });
            return;
        }

        // GET /v1/pos/orders — List orders for restaurant
        if (method === 'GET' && pathname === '/v1/pos/orders') {
            const restaurantOrders = orders.filter(o => o.restaurant_id === restaurantId);
            json(res, 200, { orders: restaurantOrders, count: restaurantOrders.length });
            return;
        }

        // POST /v1/pos/orders/:id/status — Update status
        if (method === 'POST' && pathname.match(/^\/v1\/pos\/orders\/[^/]+\/status$/)) {
            const orderId = pathname.split('/')[4];
            const order = orders.find(o => o.order_id === orderId && o.restaurant_id === restaurantId);
            if (order) {
                const statusMap = { 'PREPARING': 'IN_PROGRESS', 'READY': 'READY', 'PICKED_UP': 'FULFILLING', 'COMPLETED': 'COMPLETED' };
                order.status = statusMap[payload.status] || payload.status;
                console.log(`📋 [POS] Status Updated: ${orderId} → ${order.status}`);
                json(res, 200, { order_id: orderId, status: order.status });
            } else {
                json(res, 404, { error: 'Order not found' });
            }
            return;
        }

        // POST /v1/pos/orders/:id/fire — Force fire
        if (method === 'POST' && pathname.match(/^\/v1\/pos\/orders\/[^/]+\/fire$/)) {
            const orderId = pathname.split('/')[4];
            const order = orders.find(o => o.order_id === orderId && o.restaurant_id === restaurantId);
            if (order && (order.status === 'PENDING_NOT_SENT' || order.status === 'WAITING')) {
                order.status = 'SENT_TO_DESTINATION';
                order.vicinity = true;
                console.log(`🔥 [POS] Force Fire: ${orderId}`);
                json(res, 200, { order_id: orderId, status: 'SENT_TO_DESTINATION', fired: true });
            } else if (order) {
                json(res, 409, { error: 'Order not in a fireable state' });
            } else {
                json(res, 404, { error: 'Order not found' });
            }
            return;
        }

        // GET /v1/pos/menu — Get menu
        if (method === 'GET' && pathname === '/v1/pos/menu') {
            const restaurant = RESTAURANTS.find(r => r.restaurant_id === restaurantId);
            json(res, 200, { menu: restaurant?.menu || [], restaurant_id: restaurantId });
            return;
        }

        // POST /v1/pos/menu/sync — Sync menu
        if (method === 'POST' && pathname === '/v1/pos/menu/sync') {
            const restaurant = RESTAURANTS.find(r => r.restaurant_id === restaurantId);
            if (restaurant) {
                restaurant.menu = payload.items || [];
                console.log(`📝 [POS] Menu Synced: ${(payload.items || []).length} items for ${restaurantId}`);
            }
            json(res, 200, { synced: (payload.items || []).length, restaurant_id: restaurantId });
            return;
        }

        // POST /v1/pos/webhook — Generic webhook
        if (method === 'POST' && pathname === '/v1/pos/webhook') {
            console.log(`🔔 [POS] Webhook: ${payload.event_type || 'unknown'} from ${keyRecord.pos_system}`);
            json(res, 200, { status: 'acknowledged', event_type: payload.event_type });
            return;
        }

        json(res, 404, { error: 'POS route not found' });
    });
});

function json(res, status, data) {
    res.writeHead(status, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(data));
}

server.listen(PORT, '0.0.0.0', () => {
    console.log(`
  🍽️  Arrive Demo Mock Server
  ============================
  Running on http://0.0.0.0:${PORT}
  
  Accessible from network at: http://192.168.1.154:${PORT}
  
  This server syncs orders between:
  - Client App (localhost:5173)
  - Admin Portal (localhost:5174)
  - iOS App (192.168.1.154:${PORT})
  
  Orders are stored in memory and reset on restart.
  `);
});
