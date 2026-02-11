import { useState, useEffect, useCallback } from 'react'
import { signInWithRedirect, signOut, getCurrentUser, fetchAuthSession } from 'aws-amplify/auth'
import { Authenticator } from '@aws-amplify/ui-react'
import '@aws-amplify/ui-react/styles.css'
import './App.css'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:3001'
// Set VITE_API_BASE_URL in .env for each environment

function App() {
  return (
    <Authenticator>
      {({ signOut, user }) => (
        <MainAppContent user={user} signOut={signOut} />
      )}
    </Authenticator>
  )
}

function MainAppContent({ user, signOut }) {
  const [token, setToken] = useState(null)
  const [loading, setLoading] = useState(true)

  // Restaurant & Menu
  const [restaurants, setRestaurants] = useState([])
  const [selectedRestaurant, setSelectedRestaurant] = useState(null)
  const [menu, setMenu] = useState(null)
  const [cart, setCart] = useState([])

  // Orders
  const [myOrders, setMyOrders] = useState([])
  const [apiResponse, setApiResponse] = useState(null)


  useEffect(() => {
    fetchToken()
  }, [])

  async function fetchToken() {
    try {
      const session = await fetchAuthSession()
      const idToken = session.tokens?.idToken?.toString()
      setToken(idToken)
    } catch (err) {
      console.log('Not signed in', err)
      setToken(null)
    }
    setLoading(false)
  }

  // Fetch restaurants on load
  useEffect(() => {
    if (token) {
      fetchRestaurants()
      fetchMyOrders()
    }
  }, [token])

  // Fetch menu when restaurant selected
  useEffect(() => {
    if (token && selectedRestaurant) {
      fetchMenu(selectedRestaurant)
    }
  }, [token, selectedRestaurant])

  // Auto-refresh orders every 5 seconds
  useEffect(() => {
    if (token && myOrders.length > 0) {
      const interval = setInterval(() => {
        refreshOrderStatuses()
      }, 5000)
      return () => clearInterval(interval)
    }
  }, [token, myOrders])

  async function fetchRestaurants() {
    try {
      const res = await fetch(`${API_BASE_URL}/v1/restaurants`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      if (res.ok) {
        const data = await res.json()
        setRestaurants(data.restaurants || [])
        // Auto-select first restaurant
        if (data.restaurants?.length > 0) {
          setSelectedRestaurant(data.restaurants[0].restaurant_id)
        }
      }
    } catch (err) {
      console.error('Failed to fetch restaurants:', err)
    }
  }

  async function fetchMenu(restaurantId) {
    try {
      const res = await fetch(`${API_BASE_URL}/v1/restaurants/${restaurantId}/menu`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      if (res.ok) {
        const data = await res.json()
        setMenu(data.menu || {})
      } else {
        setMenu({ items: [] }) // No menu configured
      }
      setCart([])
    } catch (err) {
      console.error('Failed to fetch menu:', err)
      setMenu({ items: [] })
    }
  }

  async function fetchMyOrders() {
    try {
      const res = await fetch(`${API_BASE_URL}/v1/orders`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      if (res.ok) {
        const data = await res.json()
        setMyOrders(data.orders || [])
      }
    } catch (err) {
      console.error('Failed to fetch my orders:', err)
    }
  }

  async function refreshOrderStatuses() {
    const activeOrders = myOrders.filter(o =>
      !['COMPLETED', 'CANCELED', 'EXPIRED'].includes(o.status)
    )
    for (const order of activeOrders) {
      try {
        const res = await fetch(`${API_BASE_URL}/v1/orders/${order.order_id}`, {
          headers: { 'Authorization': `Bearer ${token}` }
        })
        if (res.ok) {
          const data = await res.json()
          setMyOrders(prev => prev.map(o =>
            o.order_id === order.order_id ? { ...o, status: data.status } : o
          ))
        }
      } catch (err) {
        // Silently continue
      }
    }
  }

  function addToCart(item) {
    const existing = cart.find(c => c.id === item.id)
    if (existing) {
      setCart(cart.map(c => c.id === item.id ? { ...c, qty: c.qty + 1 } : c))
    } else {
      setCart([...cart, { ...item, qty: 1 }])
    }
  }

  function removeFromCart(itemId) {
    setCart(cart.filter(c => c.id !== itemId))
  }

  async function placeOrder() {
    if (!token || !selectedRestaurant || cart.length === 0) return
    setApiResponse({ loading: true })

    try {
      const res = await fetch(`${API_BASE_URL}/v1/orders`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          restaurant_id: selectedRestaurant,
          items: cart.map(c => ({
            id: c.id,
            qty: c.qty,
            name: c.name,
            price_cents: c.price_cents || 0,
          })),
        }),
      })
      const data = await res.json()
      setApiResponse({ status: res.status, data })
      if (data.order_id) {
        setMyOrders(prev => [{ order_id: data.order_id, status: data.status }, ...prev])
        setCart([])
        alert('🎉 Order Placed Successfully!')
        setTimeout(() => {
          document.querySelector('.orders-section')?.scrollIntoView({ behavior: 'smooth' })
        }, 100)
      }
    } catch (err) {
      setApiResponse({ error: err.message })
      alert('Failed to place order: ' + err.message)
    }
  }

  async function enterVicinity(orderId) {
    setApiResponse({ loading: true })

    try {
      const res = await fetch(`${API_BASE_URL}/v1/orders/${orderId}/vicinity`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ event: 'AT_DOOR' }),
      })
      const data = await res.json()
      setApiResponse({ status: res.status, data, action: 'vicinity' })

      if (res.ok && data.status) {
        setMyOrders(prev => prev.map(o =>
          o.order_id === orderId ? { ...o, status: data.status } : o
        ))
      } else if (!res.ok) {
        setApiResponse({ status: res.status, data, action: 'vicinity', error: data.error?.message || 'Vicinity update failed' })
      }
    } catch (err) {
      setApiResponse({ error: err.message })
    }
  }

  async function cancelOrder(orderId) {
    setApiResponse({ loading: true })

    try {
      const res = await fetch(`${API_BASE_URL}/v1/orders/${orderId}/cancel`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
      })
      const data = await res.json()
      setApiResponse({ status: res.status, data, action: 'cancel' })

      if (res.ok && data.status === 'CANCELED') {
        setMyOrders(prev => prev.map(o =>
          o.order_id === orderId ? { ...o, status: 'CANCELED' } : o
        ))
      } else if (!res.ok) {
        setApiResponse({ status: res.status, data, action: 'cancel', error: data.error?.message || 'Cancel failed' })
      }
    } catch (err) {
      setApiResponse({ error: err.message })
    }
  }

  async function getOrderStatus(orderId) {
    setApiResponse({ loading: true })

    try {
      const res = await fetch(`${API_BASE_URL}/v1/orders/${orderId}`, {
        headers: { 'Authorization': `Bearer ${token}` },
      })
      const data = await res.json()
      setApiResponse({ status: res.status, data })
      setMyOrders(prev => prev.map(o =>
        o.order_id === orderId ? { ...o, status: data.status } : o
      ))
    } catch (err) {
      setApiResponse({ error: err.message })
    }
  }

  if (loading) {
    return <div className="container"><p>Loading...</p></div>
  }

  const cartTotal = cart.reduce((sum, c) => sum + (c.price_cents || 0) * c.qty, 0)

  return (
    <div className="container">
      {/* Background Washes */}
      <div className="wash-accent-1"></div>
      <div className="wash-accent-2"></div>

      <header className="artistic-header">
        <div className="header-row" style={{ width: '100%', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h1>AADI</h1>
          <div className="user-actions user-pill">
            <span className="username">{user.username?.split('_')[1]?.slice(0, 8) || 'User'}</span>
            <button onClick={() => signOut()} className="btn btn-small">Sign Out</button>
          </div>
        </div>
      </header>

      {/* Restaurant Selector */}
      <section className="restaurant-section">
        <h2>📍 Select Restaurant</h2>
        <select
          value={selectedRestaurant || ''}
          onChange={(e) => setSelectedRestaurant(e.target.value)}
          className="restaurant-select"
        >
          <option value="">Choose a restaurant...</option>
          {restaurants.map(r => (
            <option key={r.restaurant_id} value={r.restaurant_id}>
              {r.name || r.restaurant_id}
            </option>
          ))}
        </select>
      </section>

      {/* Menu */}
      {menu && selectedRestaurant && (
        <section className="menu-section">
          <h2>🍽️ Menu</h2>
          {menu.items?.length > 0 ? (
            <div className="menu-grid">
              {menu.items.map((item, idx) => (
                <div key={item.id || idx} className="menu-item organic-card">
                  <div className="item-info">
                    <span className="item-name">{item.name || item.id}</span>
                    <span className="item-price">${((item.price_cents || 0) / 100).toFixed(2)}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                    <button onClick={() => addToCart(item)} className="btn btn-add">+ Add</button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="empty-menu">No menu items available for this restaurant. Please seed data using the seed script.</p>
          )}
        </section>
      )}

      {/* Cart */}
      {cart.length > 0 && (
        <section className="cart-section" style={{ marginTop: '3rem' }}>
          <h2>🛒 Your Cart</h2>
          <div className="cart-items organic-card">
            {cart.map(item => (
              <div key={item.id} className="cart-item" style={{ borderBottom: '1px solid #eee', paddingBottom: '0.5rem', marginBottom: '0.5rem' }}>
                <span>{item.name} <span style={{ color: 'var(--accent-gold)', fontWeight: 'bold' }}>x{item.qty}</span></span>
                <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                  <span>${((item.price_cents || 0) * item.qty / 100).toFixed(2)}</span>
                  <button onClick={() => removeFromCart(item.id)} className="btn btn-remove">✕</button>
                </div>
              </div>
            ))}
            <div className="cart-total" style={{ marginTop: '1rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '2px solid var(--accent-gold)', paddingTop: '1rem' }}>
              <strong style={{ fontSize: '1.2rem' }}>Total: ${(cartTotal / 100).toFixed(2)}</strong>
              <button onClick={placeOrder} className="btn btn-primary">
                🚀 Place Order
              </button>
            </div>
          </div>
        </section>
      )}

      {/* My Orders */}
      {myOrders.length > 0 && (
        <section className="orders-section" style={{ marginTop: '3rem' }}>
          <h2>📋 My Orders</h2>
          <div className="my-orders-list">
            {myOrders.map(order => (
              <OrderCard
                key={order.order_id}
                order={order}
                onVicinity={enterVicinity}
                onCancel={cancelOrder}
                onRefresh={getOrderStatus}
              />
            ))}
          </div>
        </section>
      )}

      {/* API Response */}
      {apiResponse && (
        <section className="response-section" style={{ marginTop: '2rem', opacity: 0.7 }}>
          <h3>Last Response:</h3>
          {apiResponse.loading ? <p>Loading...</p> : (
            <pre style={{ background: '#eee', padding: '1rem', borderRadius: '12px' }}>{JSON.stringify(apiResponse, null, 2)}</pre>
          )}
        </section>
      )}
    </div>
  )
}

function OrderCard({ order, onVicinity, onCancel, onRefresh }) {
  const statusConfig = {
    'PENDING_NOT_SENT': { label: '⏳ Confirmed', color: '#f59e0b', canVicinity: true, canCancel: true },
    'WAITING': { label: '⏰ Waiting', color: '#f59e0b', canVicinity: true, canCancel: true },
    'SENT_TO_DESTINATION': { label: '📨 Sent', color: '#3b82f6' },
    'IN_PROGRESS': { label: '👨‍🍳 Cooking', color: '#8b5cf6' },
    'READY': { label: '✅ Ready!', color: '#22c55e' },
    'FULFILLING': { label: '🍽️ Serving', color: '#10b981' },
    'COMPLETED': { label: '🎉 Done', color: '#6b7280' },
    'CANCELED': { label: '❌ Canceled', color: '#ef4444' },
    'EXPIRED': { label: '⏰ Expired', color: '#ef4444' },
  }

  const config = statusConfig[order.status] || { label: order.status, color: '#6b7280' }

  return (
    <div className="my-order-card organic-card">
      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
        <span className="order-id" style={{ color: 'var(--text-muted)' }}>#{order.order_id.slice(-8)}</span>
        <span className="order-status" style={{ backgroundColor: config.color, boxShadow: '0 4px 12px rgba(0,0,0,0.1)' }}>
          {config.label}
        </span>
      </div>
      <div className="order-actions">
        {config.canVicinity && (
          <button onClick={() => onVicinity(order.order_id)} className="btn btn-vicinity" style={{ borderRadius: '20px' }}>
            📍 I'm Here
          </button>
        )}
        {config.canCancel && (
          <button onClick={() => onCancel(order.order_id)} className="btn btn-cancel" style={{ borderRadius: '20px' }}>
            ✕ Cancel
          </button>
        )}
        <button onClick={() => onRefresh(order.order_id)} className="btn btn-small">
          🔄
        </button>
      </div>
    </div>
  )
}

export default App
