import { useState, useEffect, useCallback, useRef } from 'react'
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
import * as api from './services/api'


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
  const { loading } = useAuth(signOut)

  // Restaurant & Menu
  const [restaurants, setRestaurants] = useState([])
  const [selectedRestaurant, setSelectedRestaurant] = useState(null)
  const [menu, setMenu] = useState(null)
  const [cart, setCart] = useState([])

  // Orders
  const [myOrders, setMyOrders] = useState([])
  const [orderLoading, setOrderLoading] = useState(false)
  const [statusMessage, setStatusMessage] = useState(null)
  const [customerName, setCustomerName] = useState('')
  const [customerEmail, setCustomerEmail] = useState('')

  // Navigation
  const [currentView, setCurrentView] = useState('home') // home | profile | favorites

  // Ref for stable polling callback — avoids interval churn
  const myOrdersRef = useRef(myOrders)
  useEffect(() => { myOrdersRef.current = myOrders }, [myOrders])

  // Ref guard for double-submit prevention
  const placingOrderRef = useRef(false)


  /* ── Data fetching ────────────────────────────────────────────── */

  const fetchRestaurants = useCallback(async () => {
    try {
      const list = await api.fetchRestaurants()
      setRestaurants(list)
      if (list.length > 0) {
        setSelectedRestaurant(list[0].restaurant_id)
      }
    } catch (err) {
      console.error('Failed to fetch restaurants:', err)
    }
  }, [])

  const fetchMenu = useCallback(async (restaurantId) => {
    try {
      const items = await api.fetchMenu(restaurantId)
      setMenu({ items })
    } catch (err) {
      console.error('Failed to fetch menu:', err)
      setMenu({ items: [] })
    }
    setCart([])
  }, [])

  const fetchMyOrders = useCallback(async () => {
    try {
      const orders = await api.fetchOrders()
      setMyOrders(orders)
    } catch (err) {
      console.error('Failed to fetch my orders:', err)
    }
  }, [])

  const fallbackCustomerName = useCallback(() => {
    if (!user?.username) return ''
    const suffix = user.username.split('_')[1] || user.username
    return (suffix || '').trim()
  }, [user])

  const fetchCustomerProfileName = useCallback(async () => {
    try {
      const data = await api.getUserProfile()
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
  }, [])

  const refreshOrderStatuses = useCallback(async () => {
    const activeOrders = myOrdersRef.current.filter(o =>
      !['COMPLETED', 'CANCELED', 'EXPIRED'].includes(o.status)
    )
    for (const order of activeOrders) {
      try {
        const data = await api.getOrderStatus(order.order_id)
        setMyOrders(prev => prev.map(o =>
          o.order_id === order.order_id
            ? { ...o, status: data.status, arrival_status: data.arrival_status }
            : o
        ))
      } catch (_err) {
        // Silently continue
      }
    }
  }, [])


  /* ── Effects ──────────────────────────────────────────────────── */

  useEffect(() => {
    if (!loading) {
      fetchRestaurants()
      fetchMyOrders()
      fetchCustomerProfileName()
    }
  }, [loading, fetchRestaurants, fetchMyOrders, fetchCustomerProfileName])

  useEffect(() => {
    if (!loading && selectedRestaurant) {
      fetchMenu(selectedRestaurant)
    }
  }, [loading, selectedRestaurant, fetchMenu])

  useEffect(() => {
    if (!loading && myOrders.length > 0) {
      const interval = setInterval(refreshOrderStatuses, 5000)
      return () => clearInterval(interval)
    }
  }, [loading, myOrders.length, refreshOrderStatuses])


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
    if (placingOrderRef.current || !selectedRestaurant || cart.length === 0) return
    placingOrderRef.current = true
    setOrderLoading(true)
    setStatusMessage(null)

    try {
      const latestProfileName = await fetchCustomerProfileName()
      const resolvedCustomerName = latestProfileName || customerName || fallbackCustomerName() || 'Guest'

      const { ok, data } = await api.placeOrder({
        restaurant_id: selectedRestaurant,
        customer_name: resolvedCustomerName,
        items: cart.map(c => ({
          id: c.id,
          qty: c.qty,
          name: c.name,
          price_cents: c.price_cents || 0,
        })),
      })
      if (ok && data.order_id) {
        setMyOrders(prev => [{ order_id: data.order_id, status: data.status }, ...prev])
        setCart([])
        setStatusMessage({ type: 'success', text: 'Order placed successfully!' })
        setTimeout(() => {
          document.querySelector('.orders-section')?.scrollIntoView({ behavior: 'smooth' })
        }, 100)
      } else {
        setStatusMessage({ type: 'error', text: data?.error || 'Failed to place order' })
      }
    } catch (err) {
      console.error('Failed to place order:', err)
      setStatusMessage({ type: 'error', text: 'Failed to place order. Please try again.' })
    } finally {
      placingOrderRef.current = false
      setOrderLoading(false)
    }
  }

  async function enterVicinity(orderId) {
    try {
      const { ok, data } = await api.enterVicinity(orderId)
      if (ok && data.status) {
        setMyOrders(prev => prev.map(o =>
          o.order_id === orderId
            ? { ...o, status: data.status, arrival_status: data.arrival_status || o.arrival_status }
            : o
        ))
        setStatusMessage({ type: 'success', text: 'Arrival confirmed!' })
      } else {
        setStatusMessage({ type: 'error', text: data?.error || 'Failed to update vicinity' })
      }
    } catch (err) {
      console.error('Failed to enter vicinity:', err)
      setStatusMessage({ type: 'error', text: 'Failed to update vicinity. Please try again.' })
    }
  }

  async function cancelOrder(orderId) {
    try {
      const { ok, data } = await api.cancelOrder(orderId)
      if (ok && data.status === 'CANCELED') {
        setMyOrders(prev => prev.map(o =>
          o.order_id === orderId ? { ...o, status: 'CANCELED' } : o
        ))
      } else {
        setStatusMessage({ type: 'error', text: data?.error || 'Failed to cancel order' })
      }
    } catch (err) {
      console.error('Failed to cancel order:', err)
      setStatusMessage({ type: 'error', text: 'Failed to cancel order. Please try again.' })
    }
  }

  async function handleGetOrderStatus(orderId) {
    try {
      const data = await api.getOrderStatus(orderId)
      setMyOrders(prev => prev.map(o =>
        o.order_id === orderId
          ? { ...o, status: data.status, arrival_status: data.arrival_status }
          : o
      ))
    } catch (err) {
      console.error('Failed to get order status:', err)
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

      {statusMessage && (
        <div style={{ padding: '10px 16px', marginBottom: '1rem', borderRadius: 8, background: statusMessage.type === 'error' ? '#fce4ec' : '#e8f5e9', color: statusMessage.type === 'error' ? '#c62828' : '#2e7d32', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span>{statusMessage.text}</span>
          <button onClick={() => setStatusMessage(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '1rem' }}>✕</button>
        </div>
      )}

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

          <Cart cart={cart} onRemove={removeFromCart} onPlaceOrder={placeOrder} isLoading={orderLoading} />

          <OrderList
            orders={myOrders}
            onVicinity={enterVicinity}
            onCancel={cancelOrder}
            onRefresh={handleGetOrderStatus}
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
    </div>
  )
}

export default App
