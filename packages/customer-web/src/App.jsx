import { useState, useEffect, useCallback } from 'react'
import { Authenticator } from '@aws-amplify/ui-react'
import '@aws-amplify/ui-react/styles.css'
import './App.css'

import { useAuth } from './hooks/useAuth'
import RestaurantSelector from './components/RestaurantSelector'
import MenuGrid from './components/MenuGrid'
import Cart from './components/Cart'
import OrderList from './components/OrderList'
import Profile from './components/Profile'
import Favorites from './components/Favorites'
import { RESTAURANTS_API_URL, ORDERS_API_URL, USERS_API_URL } from './config'


function CustomerAuthHeader() {
  return (
    <div className="auth-brand-header">
      <img src="/logo_icon_stylized.png" alt="AADI logo" className="auth-brand-logo" />
      <div>
        <h2>AADI</h2>
        <p>Customer Portal</p>
      </div>
    </div>
  )
}

const authComponents = {
  Header: CustomerAuthHeader,
}

function App() {
  return (
    <Authenticator className="customer-auth-shell" components={authComponents}>
      {({ signOut, user }) => (
        <MainAppContent user={user} signOut={signOut} />
      )}
    </Authenticator>
  )
}


function MainAppContent({ user, signOut }) {
  const { token, loading } = useAuth(signOut)

  // Restaurant & Menu
  const [restaurants, setRestaurants] = useState([])
  const [selectedRestaurant, setSelectedRestaurant] = useState(null)
  const [menu, setMenu] = useState(null)
  const [cart, setCart] = useState([])

  // Orders
  const [myOrders, setMyOrders] = useState([])
  const [apiResponse, setApiResponse] = useState(null)
  const [customerName, setCustomerName] = useState('')
  const [customerEmail, setCustomerEmail] = useState('')

  // Navigation
  const [currentView, setCurrentView] = useState('home') // home | profile | favorites


  /* ── Data fetching ────────────────────────────────────────────── */

  const fetchRestaurants = useCallback(async () => {
    try {
      const res = await fetch(`${RESTAURANTS_API_URL}/v1/restaurants`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      if (res.ok) {
        const data = await res.json()
        setRestaurants(data.restaurants || [])
        if (data.restaurants?.length > 0) {
          setSelectedRestaurant(data.restaurants[0].restaurant_id)
        }
      }
    } catch (err) {
      console.error('Failed to fetch restaurants:', err)
    }
  }, [token])

  const fetchMenu = useCallback(async (restaurantId) => {
    try {
      const res = await fetch(`${RESTAURANTS_API_URL}/v1/restaurants/${restaurantId}/menu`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      if (res.ok) {
        const data = await res.json()
        const rawItems = data.items || data.menu?.items || []
        const items = rawItems.map(item => ({
          ...item,
          price_cents: item.price_cents !== undefined
            ? item.price_cents
            : (item.price ? Math.round(Number(item.price) * 100) : 0)
        }))
        setMenu({ items })
      } else {
        setMenu({ items: [] })
      }
      setCart([])
    } catch (err) {
      console.error('Failed to fetch menu:', err)
      setMenu({ items: [] })
    }
  }, [token])

  const fetchMyOrders = useCallback(async () => {
    try {
      const res = await fetch(`${ORDERS_API_URL}/v1/orders`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      if (res.ok) {
        const data = await res.json()
        setMyOrders(data.orders || [])
      }
    } catch (err) {
      console.error('Failed to fetch my orders:', err)
    }
  }, [token])

  const fallbackCustomerName = useCallback(() => {
    if (!user?.username) return ''
    const suffix = user.username.split('_')[1] || user.username
    return (suffix || '').trim()
  }, [user])

  const fetchCustomerProfileName = useCallback(async () => {
    if (!token) return null
    try {
      const res = await fetch(`${USERS_API_URL}/v1/users/me`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      if (!res.ok) return null

      const data = await res.json()
      const profileEmail = (data?.email || '').trim()
      const profileName = (data?.name || '').trim()
      if (profileEmail) {
        setCustomerEmail(profileEmail)
      }
      if (profileName) {
        setCustomerName(profileName)
        return profileName
      }
    } catch {
      // Non-blocking: we can still place orders with a fallback name.
    }
    return null
  }, [token])

  const refreshOrderStatuses = useCallback(async () => {
    const activeOrders = myOrders.filter(o =>
      !['COMPLETED', 'CANCELED', 'EXPIRED'].includes(o.status)
    )
    for (const order of activeOrders) {
      try {
        const res = await fetch(`${ORDERS_API_URL}/v1/orders/${order.order_id}`, {
          headers: { 'Authorization': `Bearer ${token}` }
        })
        if (res.ok) {
          const data = await res.json()
          setMyOrders(prev => prev.map(o =>
            o.order_id === order.order_id ? { ...o, status: data.status } : o
          ))
        }
      } catch (_err) {
        // Silently continue
      }
    }
  }, [token, myOrders])


  /* ── Effects ──────────────────────────────────────────────────── */

  useEffect(() => {
    if (token) {
      fetchRestaurants()
      fetchMyOrders()
      fetchCustomerProfileName()
    }
  }, [token, fetchRestaurants, fetchMyOrders, fetchCustomerProfileName])

  useEffect(() => {
    if (token && selectedRestaurant) {
      fetchMenu(selectedRestaurant)
    }
  }, [token, selectedRestaurant, fetchMenu])

  useEffect(() => {
    if (token && myOrders.length > 0) {
      const interval = setInterval(refreshOrderStatuses, 5000)
      return () => clearInterval(interval)
    }
  }, [token, myOrders, refreshOrderStatuses])


  /* ── Cart helpers ─────────────────────────────────────────────── */

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


  /* ── Order actions ────────────────────────────────────────────── */

  async function placeOrder() {
    if (!token || !selectedRestaurant || cart.length === 0) return
    setApiResponse({ loading: true })

    try {
      const latestProfileName = await fetchCustomerProfileName()
      const resolvedCustomerName = latestProfileName || customerName || fallbackCustomerName() || 'Guest'

      const res = await fetch(`${ORDERS_API_URL}/v1/orders`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          restaurant_id: selectedRestaurant,
          customer_name: resolvedCustomerName,
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
      const res = await fetch(`${ORDERS_API_URL}/v1/orders/${orderId}/vicinity`, {
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
      }
    } catch (err) {
      setApiResponse({ error: err.message })
    }
  }

  async function cancelOrder(orderId) {
    setApiResponse({ loading: true })
    try {
      const res = await fetch(`${ORDERS_API_URL}/v1/orders/${orderId}/cancel`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
      })
      const data = await res.json()
      setApiResponse({ status: res.status, data, action: 'cancel' })
      if (res.ok && data.status === 'CANCELED') {
        setMyOrders(prev => prev.map(o =>
          o.order_id === orderId ? { ...o, status: 'CANCELED' } : o
        ))
      }
    } catch (err) {
      setApiResponse({ error: err.message })
    }
  }

  async function getOrderStatus(orderId) {
    setApiResponse({ loading: true })
    try {
      const res = await fetch(`${ORDERS_API_URL}/v1/orders/${orderId}`, {
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


  /* ── Render ───────────────────────────────────────────────────── */

  if (loading) {
    return <div className="container"><p>Loading...</p></div>
  }

  const cognitoLoginId = (user?.signInDetails?.loginId || '').trim()
  const fallbackEmail = cognitoLoginId.includes('@')
    ? cognitoLoginId
    : ((user?.username || '').includes('@') ? user.username : '')
  const headerName = (customerName || '').trim()
  const headerEmail = (customerEmail || fallbackEmail || '').trim()
  const headerPrimary = headerName || headerEmail || user?.username || 'Customer'
  const headerSecondary = headerName && headerEmail ? headerEmail : ''

  return (
    <div className="container">
      {/* Background Washes */}
      <div className="wash-accent-1"></div>
      <div className="wash-accent-2"></div>

      <header className="artistic-header">
        <div className="header-row" style={{ width: '100%', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div className="brand-lockup cursor-pointer" onClick={() => setCurrentView('home')}>
            <img src="/logo_icon_stylized.png" alt="AADI logo" className="brand-logo" />
            <div>
              <h1>AADI</h1>
              <p className="brand-subtitle">Order Ahead. Arrive Perfectly.</p>
            </div>
          </div>

          <nav className="nav-tabs">
            <button className={`nav-tab ${currentView === 'home' ? 'active' : ''}`} onClick={() => setCurrentView('home')}>Home</button>
            <button className={`nav-tab ${currentView === 'favorites' ? 'active' : ''}`} onClick={() => setCurrentView('favorites')}>Favorites</button>
            <button className={`nav-tab ${currentView === 'profile' ? 'active' : ''}`} onClick={() => setCurrentView('profile')}>Profile</button>
          </nav>

          <div className="user-actions user-pill">
            <div className="user-identity">
              <span className="user-primary">{headerPrimary}</span>
              {headerSecondary && <span className="user-secondary">{headerSecondary}</span>}
            </div>
            <button onClick={() => signOut()} className="btn btn-small">Sign Out</button>
          </div>
        </div>
      </header>

      {currentView === 'home' && (
        <>
          <RestaurantSelector
            restaurants={restaurants}
            selectedId={selectedRestaurant}
            onSelect={setSelectedRestaurant}
          />

          {selectedRestaurant && (
            <MenuGrid menu={menu} onAddToCart={addToCart} />
          )}

          <Cart cart={cart} onRemove={removeFromCart} onPlaceOrder={placeOrder} />

          <OrderList
            orders={myOrders}
            onVicinity={enterVicinity}
            onCancel={cancelOrder}
            onRefresh={getOrderStatus}
          />
        </>
      )}

      {currentView === 'profile' && (
        <Profile user={user} signOut={signOut} />
      )}

      {currentView === 'favorites' && (
        <Favorites
          restaurants={restaurants}
          onSelectRestaurant={(id) => {
            setSelectedRestaurant(id);
            setCurrentView('home');
          }}
        />
      )}

      {/* Debug API Response */}
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

export default App
