import { useState, useEffect, useCallback, useRef } from 'react'
import { getCurrentUser, fetchAuthSession, fetchUserAttributes } from 'aws-amplify/auth'
import { Authenticator } from '@aws-amplify/ui-react'
import '@aws-amplify/ui-react/styles.css'
import { API_BASE_URL } from './aws-exports'
import './App.css'
import StatsBar from './components/StatsBar'
import KanbanBoard, { Order } from './components/KanbanBoard'

interface Restaurant {
  restaurant_id: string;
  name: string;
}

interface User {
  username: string;
}


function App() {
  // --- STATE ---
  const [_user, setUser] = useState<User | null>(null)
  const [token, setToken] = useState<string | null>(null)
  const [restaurants, setRestaurants] = useState<Restaurant[]>([])
  const [selectedRestaurant, setSelectedRestaurant] = useState<string | null>(null)
  const [orders, setOrders] = useState<Order[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [lastRefresh, setLastRefresh] = useState<string | null>(null)
  const [filter, setFilter] = useState('active')
  const [newOrderAlert, setNewOrderAlert] = useState(false)
  const prevOrderIds = useRef<Set<string>>(new Set())

  // RBAC State
  const [_assignedRestaurantId, setAssignedRestaurantId] = useState<string | null>(null)

  useEffect(() => {
    checkUser()
  }, [])

  async function checkUser() {
    try {
      const currentUser = await getCurrentUser()
      setUser(currentUser)

      const session = await fetchAuthSession()
      const idToken = session.tokens?.idToken?.toString() ?? null
      setToken(idToken)

      // RBAC Check
      const attrs = await fetchUserAttributes()
      const role = attrs['custom:role']
      const RestId = attrs['custom:restaurant_id']

      if (role !== 'admin') {
        // Access denied logic here
      } else {
        if (RestId) {
          setAssignedRestaurantId(RestId || null)
          setSelectedRestaurant(RestId || null) // Auto-select
        }
      }

    } catch (err) {
      console.error(err)
      setUser(null)
      setToken(null)
    }
    setLoading(false)
  }

  // Fetch restaurants when token is available
  useEffect(() => {
    if (token) {
      fetchRestaurants()
    }
  }, [token])

  async function fetchRestaurants() {
    try {
      const res = await fetch(`${API_BASE_URL}/v1/restaurants`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      if (res.ok) {
        const data = await res.json()
        const rests = data.restaurants || []
        setRestaurants(rests)
        // Auto-select first restaurant
        if (rests.length > 0 && !selectedRestaurant) {
          setSelectedRestaurant(rests[0].restaurant_id)
        }
      }
    } catch (err) {
      console.error('Failed to fetch restaurants:', err)
    }
  }

  const fetchOrders = useCallback(async () => {
    if (!token || !selectedRestaurant) return
    setError(null)

    try {
      // Single fetch for all orders — no status filter needed
      // Backend returns all orders for the restaurant when status is omitted
      const res = await fetch(`${API_BASE_URL}/v1/restaurants/${selectedRestaurant}/orders`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      const fetchedOrders: Order[] = []
      if (res.ok) {
        const data = await res.json()
        fetchedOrders.push(...(data.orders || []))
      }

      // Check for new SENT_TO_DESTINATION orders
      const currentSentIds = new Set<string>(
        fetchedOrders
          .filter((o: Order) => o.status === 'SENT_TO_DESTINATION')
          .map((o: Order) => o.order_id)
      )

      const hasNewOrder = [...currentSentIds].some((id: string) => !prevOrderIds.current.has(id))
      if (hasNewOrder && prevOrderIds.current.size > 0) {
        playNotificationSound()
        setNewOrderAlert(true)
        setTimeout(() => setNewOrderAlert(false), 3000)
      }
      prevOrderIds.current = currentSentIds

      setOrders(fetchedOrders)
      setLastRefresh(new Date().toLocaleTimeString())
    } catch (err: any) {
      setError(err.message)
    }
  }, [token, selectedRestaurant])

  function playNotificationSound() {
    try {
      const AudioContext = window.AudioContext || (window as any).webkitAudioContext
      const audioContext = new AudioContext()
      const oscillator = audioContext.createOscillator()
      const gainNode = audioContext.createGain()

      oscillator.connect(gainNode)
      gainNode.connect(audioContext.destination)

      oscillator.frequency.value = 880
      oscillator.type = 'sine'
      gainNode.gain.value = 0.3

      oscillator.start()
      setTimeout(() => {
        oscillator.stop()
        audioContext.close()
      }, 200)
    } catch (e) {
      console.warn('Audio not supported:', e)
    }
  }

  // Fetch orders when restaurant changes
  useEffect(() => {
    if (token && selectedRestaurant) {
      // Reset when switching restaurants
      prevOrderIds.current = new Set()
      fetchOrders()
      const interval = setInterval(fetchOrders, 5000)
      return () => clearInterval(interval)
    }
  }, [token, selectedRestaurant, fetchOrders])


  async function handleStatusUpdate(orderId: string, newStatus: string) {
    try {
      const res = await fetch(`${API_BASE_URL}/v1/restaurants/${selectedRestaurant}/orders/${orderId}/status`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ status: newStatus })
      })
      if (res.ok) fetchOrders()
    } catch (err: any) {
      setError(err.message || 'Update failed')
    }
  }

  // Counts
  const pendingCount = orders.filter(o => o.status === 'PENDING_NOT_SENT').length
  const activeCount = orders.filter(o => ['SENT_TO_DESTINATION', 'IN_PROGRESS', 'READY', 'FULFILLING'].includes(o.status)).length
  const sentCount = orders.filter(o => o.status === 'SENT_TO_DESTINATION').length


  if (loading) {
    return <div className="container"><p>Loading...</p></div>
  }

  return (
    <Authenticator>
      {({ user, signOut }) => (
        <div className={`container ${newOrderAlert ? 'new-order-flash' : ''}`}>
          {/* Background Washes */}
          <div className="wash-accent-1"></div>
          <div className="wash-accent-2"></div>

          <header className="artistic-header">
            <div className="header-content" style={{ width: '100%', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h1>🍽️ {restaurants.find(r => r.restaurant_id === selectedRestaurant)?.name || 'AADI Restaurant Portal'}</h1>
              <div className="user-info">
                <span style={{ marginRight: '12px', color: '#94a3b8' }}>
                  {user?.username}
                </span>
                <button onClick={signOut} className="btn btn-small">
                  Sign Out
                </button>
              </div>
            </div>
          </header>

          {/* Restaurant Picker */}
          <section className="restaurant-picker">
            <label>📍 Managing Restaurant:</label>

            <select
              value={selectedRestaurant || ''}
              onChange={(e) => setSelectedRestaurant(e.target.value)}
              className="restaurant-select"
            >
              {restaurants.map(r => (
                <option key={r.restaurant_id} value={r.restaurant_id}>
                  {r.name || r.restaurant_id}
                </option>
              ))}
            </select>

            <span className="restaurant-id">ID: {selectedRestaurant}</span>
          </section>

          <StatsBar sentCount={sentCount} activeCount={activeCount} pendingCount={pendingCount} />

          <div className="toolbar">
            <button onClick={fetchOrders} className="btn">🔄 Refresh</button>
            <span className="last-update">Last: {lastRefresh || 'Never'}</span>
            {error && <span className="error">⚠️ {error}</span>}
          </div>

          <div className="filter-tabs">
            <button className={`tab ${filter === 'active' ? 'active' : ''}`} onClick={() => setFilter('active')}>
              🔥 Active ({activeCount})
            </button>
            <button className={`tab ${filter === 'pending' ? 'active' : ''}`} onClick={() => setFilter('pending')}>
              ⏳ Pending ({pendingCount})
            </button>
            <button className={`tab ${filter === 'all' ? 'active' : ''}`} onClick={() => setFilter('all')}>
              All ({orders.length})
            </button>
            <button className={`tab ${filter === 'completed' ? 'active' : ''}`} onClick={() => setFilter('completed')}>
              ✅ Done
            </button>
          </div>

          {newOrderAlert && (
            <div className="new-order-banner">
              🔔 NEW ORDER RECEIVED!
            </div>
          )}

          <KanbanBoard orders={orders.filter(o => {
            if (filter === 'active') return ['SENT_TO_DESTINATION', 'IN_PROGRESS', 'READY', 'FULFILLING'].includes(o.status)
            if (filter === 'pending') return o.status === 'PENDING_NOT_SENT'
            if (filter === 'completed') return o.status === 'COMPLETED'
            return true // 'all'
          })} handleStatusUpdate={handleStatusUpdate} />
        </div>
      )}
    </Authenticator>
  )
}

export default App
