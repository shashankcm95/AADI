import { useState, useEffect, useCallback, useRef } from 'react'
import { fetchAuthSession, fetchUserAttributes } from 'aws-amplify/auth'
import { API_BASE_URL, ORDERS_API_URL } from '../aws-exports'
import '../App.css'
import StatsBar from './StatsBar'
import KanbanBoard, { Order } from './KanbanBoard'
import RestaurantForm from './RestaurantForm'
import AdminDashboard from './AdminDashboard'
import MenuIngestion from './MenuIngestion'
import CapacitySettings from './CapacitySettings'
import RestaurantImageManager from './RestaurantImageManager'

// Interfaces
interface Restaurant {
    restaurant_id: string;
    name: string;
    active?: boolean;
    restaurant_image_keys?: string[];
    restaurant_images?: string[];
}


interface DashboardProps {
    user: any;
    signOut: (() => void) | undefined;
}

export default function Dashboard({ user, signOut }: DashboardProps) {
    // --- STATE ---
    const [token, setToken] = useState<string | null>(null)
    const [restaurants, setRestaurants] = useState<Restaurant[]>([])
    const [selectedRestaurant, setSelectedRestaurant] = useState<string | null>(null)
    const [orders, setOrders] = useState<Order[]>([])
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)
    const [lastRefresh, setLastRefresh] = useState<string | null>(null)
    const [filter, setFilter] = useState('active')
    const [newOrderAlert, setNewOrderAlert] = useState(false)
    const [showAddRestaurant, setShowAddRestaurant] = useState(false)

    // Menu Management State
    const [showMenu, setShowMenu] = useState(false)
    const [menuItems, setMenuItems] = useState<any[]>([])

    // Capacity Management State
    const [showCapacity, setShowCapacity] = useState(false)
    const [showImages, setShowImages] = useState(false)

    const prevOrderIds = useRef<Set<string>>(new Set())

    // RBAC State
    const [_assignedRestaurantId, setAssignedRestaurantId] = useState<string | null>(null)
    const [isAdmin, setIsAdmin] = useState(false)

    useEffect(() => {
        checkUser()
    }, [])

    async function checkUser() {
        try {
            const session = await fetchAuthSession()
            const idToken = session.tokens?.idToken?.toString() ?? null
            setToken(idToken)

            // RBAC Check
            const attrs = await fetchUserAttributes()
            const role = attrs['custom:role']
            const RestId = attrs['custom:restaurant_id']

            // console.log("RBAC Check:", { role, RestId })

            if (role === 'admin') {
                // Super Admin - no restrictions
                setAssignedRestaurantId(null)
                setIsAdmin(true)
            } else if (role === 'restaurant_admin') {
                // Restaurant Admin - restricted to specific restaurant
                if (RestId) {
                    setAssignedRestaurantId(RestId)
                    setSelectedRestaurant(RestId)
                } else {
                    console.error("Restaurant Admin has no assigned restaurant!")
                }
            } else {
                // Access denied or customer
                console.error("Access Denied: Unknown Role", role)
                alert("Access Denied: Customers cannot access the Admin Portal.")
                if (signOut) signOut()
                return
            }

        } catch (err) {
            console.error(err)
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
            // If we have an assigned restaurant, we don't necessarily need to fetch the whole list 
            // unless we want the name. But GET /v1/restaurants handles the RBAC filtering anyway.
            const res = await fetch(`${API_BASE_URL}/v1/restaurants`, {
                headers: { 'Authorization': `Bearer ${token}` }
            })
            if (res.ok) {
                const data = await res.json()
                const rests = data.restaurants || []
                setRestaurants(rests)

                // For restaurant_admin, selectedRestaurant is already set in checkUser.
                // But we want to ensure we have the NAME from the list.
                if (rests.length > 0 && !selectedRestaurant) {
                    // If Super Admin and nothing selected, pick first
                    setSelectedRestaurant(rests[0].restaurant_id)
                }
            }
        } catch (err) {
            console.error('Failed to fetch restaurants:', err)
        }
    }

    // Auto-Activation: Run when we have BOTH the restaurant list and the assigned ID
    useEffect(() => {
        if (_assignedRestaurantId && restaurants.length > 0) {
            const myRestaurant = restaurants.find(r => r.restaurant_id === _assignedRestaurantId)
            if (myRestaurant && !myRestaurant.active) {
                // console.log("First login detected (Restaurant Inactive). Activating...")
                activateRestaurant(_assignedRestaurantId)
            }
        }
    }, [_assignedRestaurantId, restaurants])

    async function activateRestaurant(id: string) {
        try {
            await fetch(`${API_BASE_URL}/v1/restaurants/${id}`, {
                method: 'PUT',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ active: true })
            })
            // console.log("Restaurant Activated!")
            // Refresh to show active status
            fetchRestaurants()
        } catch (e) {
            console.error("Failed to activate restaurant:", e)
        }
    }

    const fetchOrders = useCallback(async () => {
        if (!token || !selectedRestaurant) return
        setError(null)

        try {
            // console.log("Fetching orders from:", ORDERS_API_URL)
            const res = await fetch(`${ORDERS_API_URL}/v1/restaurants/${selectedRestaurant}/orders`, {
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

    const fetchMenu = useCallback(async () => {
        if (!token || !selectedRestaurant) return
        try {
            const res = await fetch(`${API_BASE_URL}/v1/restaurants/${selectedRestaurant}/menu`, {
                headers: { 'Authorization': `Bearer ${token}` }
            })
            if (res.ok) {
                const data = await res.json()
                setMenuItems(data.items || [])
            } else {
                setMenuItems([])
            }
        } catch (e) {
            console.error("Failed to fetch menu:", e)
        }
    }, [token, selectedRestaurant])

    const selectedRestaurantData = restaurants.find(r => r.restaurant_id === selectedRestaurant) || null


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

    async function handleSaveRestaurantImages(keys: string[]) {
        if (!token || !selectedRestaurant) return

        const response = await fetch(`${API_BASE_URL}/v1/restaurants/${selectedRestaurant}`, {
            method: 'PUT',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                restaurant_image_keys: keys,
            }),
        })

        if (!response.ok) {
            const payload = await response.json().catch(() => null)
            throw new Error(payload?.error || 'Failed to save restaurant images.')
        }

        await fetchRestaurants()
    }

    // Fetch orders when restaurant changes
    useEffect(() => {
        if (token && selectedRestaurant) {
            prevOrderIds.current = new Set()
            fetchOrders()
            // If looking at menu, fetch menu
            if (showMenu) fetchMenu()

            const interval = setInterval(fetchOrders, 5000)
            return () => clearInterval(interval)
        }
    }, [token, selectedRestaurant, fetchOrders, showMenu, fetchMenu])


    async function handleStatusUpdate(orderId: string, newStatus: string) {
        try {
            const res = await fetch(`${ORDERS_API_URL}/v1/restaurants/${selectedRestaurant}/orders/${orderId}/status`, {
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
        return <div className="container"><p>Loading Dashboard...</p></div>
    }

    if (isAdmin) {
        return <AdminDashboard signOut={signOut || (() => { })} />
    }

    return (
        <div className={`container ${newOrderAlert ? 'new-order-flash' : ''}`}>
            {/* Background Washes */}
            <div className="wash-accent-1"></div>
            <div className="wash-accent-2"></div>

            <header className="artistic-header">
                <div className="header-content" style={{ width: '100%', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div className="brand-head">
                        <img
                            src="/logo_icon_stylized.png"
                            alt="AADI logo"
                            className="brand-logo"
                        />
                        <div>
                            <h1>{restaurants.find(r => r.restaurant_id === selectedRestaurant)?.name || 'AADI Restaurant Portal'}</h1>
                            <p className="brand-subline">Restaurant operations</p>
                        </div>
                    </div>
                    <div className="user-info">
                        <span style={{ marginRight: '12px', color: 'rgba(255,255,255,0.92)' }}>
                            {user?.username}
                        </span>
                        <button onClick={signOut} className="btn btn-small">
                            Sign Out
                        </button>
                    </div>
                </div>
            </header>

            {/* Inactive Warning & Manual Activation */}
            {restaurants.find(r => r.restaurant_id === selectedRestaurant)?.active === false && (
                <div className="warning-banner" style={{ background: '#f59e0b', color: 'black', padding: '1rem', textAlign: 'center', marginBottom: '1rem' }}>
                    <strong>⚠️ Your restaurant is currently Inactive.</strong> Customers cannot see it.
                    <button
                        onClick={() => selectedRestaurant && activateRestaurant(selectedRestaurant)}
                        className="btn btn-small"
                        style={{ marginLeft: '1rem', background: 'white', color: 'black', border: 'none' }}
                    >
                        🚀 Activate Now
                    </button>
                    {error && <div style={{ color: 'red', marginTop: '0.5rem' }}>{error}</div>}
                </div>
            )}

            {/* Restaurant Picker & Toolbar */}
            <section className="restaurant-picker" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                    <label>📍 Managing Restaurant:</label>

                    {/* Only show picker if NOT assigned to a specific restaurant */}
                    {!_assignedRestaurantId ? (
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
                    ) : (
                        <span style={{ fontWeight: 'bold', marginLeft: '0.5rem', color: '#e2e8f0' }}>
                            {restaurants.find(r => r.restaurant_id === _assignedRestaurantId)?.name || 'My Restaurant'}
                        </span>
                    )}

                    {/* Show Add Button if NOT restricted to a specific restaurant */}
                    {!_assignedRestaurantId && (
                        <button
                            onClick={() => setShowAddRestaurant(true)}
                            className="btn btn-small btn-primary"
                            style={{ marginLeft: '1rem' }}
                        >
                            + Add Restaurant
                        </button>
                    )}

                    {selectedRestaurant && <span className="restaurant-id">ID: {selectedRestaurant}</span>}
                </div>

                {selectedRestaurant && (
                    <>
                        <button
                            onClick={() => {
                                if (!showMenu) fetchMenu()
                                setShowMenu(prev => !prev)
                                setShowCapacity(false)
                                setShowImages(false)
                            }}
                            className="btn btn-secondary"
                            style={{ background: showMenu ? '#e2e8f0' : undefined, color: showMenu ? 'black' : undefined, marginLeft: '0.5rem' }}
                        >
                            {showMenu ? 'Close Menu' : '📜 Manage Menu'}
                        </button>
                        <button
                            onClick={() => {
                                setShowCapacity(true)
                                setShowMenu(false)
                                setShowImages(false)
                            }}
                            className="btn btn-secondary"
                            style={{ marginLeft: '0.5rem' }}
                        >
                            ⚙️ Capacity
                        </button>
                        <button
                            onClick={() => {
                                setShowImages(prev => {
                                    const next = !prev
                                    if (next) {
                                        setShowMenu(false)
                                        setShowCapacity(false)
                                    }
                                    return next
                                })
                            }}
                            className="btn btn-secondary"
                            style={{ marginLeft: '0.5rem', background: showImages ? '#e2e8f0' : undefined, color: showImages ? 'black' : undefined }}
                        >
                            {showImages ? 'Close Images' : '🖼️ Images'}
                        </button>
                    </>
                )}
            </section>

            {showAddRestaurant && (
                <RestaurantForm
                    token={token}
                    onSuccess={() => {
                        setShowAddRestaurant(false)
                        fetchRestaurants()
                    }}
                    onCancel={() => setShowAddRestaurant(false)}
                />
            )}

            {/* Menu Management View */}
            {showMenu && token && selectedRestaurant && (
                <div className="menu-management-section" style={{ marginBottom: '2rem' }}>
                    <MenuIngestion
                        restaurantId={selectedRestaurant}
                        token={token}
                        onSuccess={fetchMenu}
                    />

                    <div style={{ marginTop: '1rem', background: 'white', padding: '1rem', borderRadius: '8px', boxShadow: '0 2px 5px rgba(0,0,0,0.05)' }}>
                        <h3>Current Menu ({menuItems.length} items)</h3>
                        {menuItems.length === 0 ? (
                            <p>No items found. Import a menu to get started.</p>
                        ) : (
                            <table className="admin-table">
                                <thead>
                                    <tr>
                                        <th>Category</th>
                                        <th>Name</th>
                                        <th>Price</th>
                                        <th>Description</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {/* Sort by Category, then Name */}
                                    {[...menuItems]
                                        .sort((a, b) => (a.category || '').localeCompare(b.category || '') || (a.name || '').localeCompare(b.name || ''))
                                        .map((item, idx) => (
                                            <tr key={idx}>
                                                <td style={{ fontWeight: 'bold', color: '#4f46e5' }}>{item.category}</td>
                                                <td>{item.name}</td>
                                                <td>${parseFloat(item.price)}</td>
                                                <td style={{ color: '#666', fontSize: '0.9em' }}>{item.description}</td>
                                            </tr>
                                        ))}
                                </tbody>
                            </table>
                        )}
                    </div>
                </div>
            )}

            {/* Capacity Settings Modal */}
            {showCapacity && token && selectedRestaurant && (
                <CapacitySettings
                    restaurantId={selectedRestaurant}
                    token={token}
                    onClose={() => setShowCapacity(false)}
                />
            )}

            {showImages && token && selectedRestaurant && selectedRestaurantData && (
                <div style={{ marginBottom: '1.5rem' }}>
                    <RestaurantImageManager
                        token={token}
                        restaurantId={selectedRestaurant}
                        initialImageKeys={selectedRestaurantData.restaurant_image_keys || []}
                        initialImageUrls={selectedRestaurantData.restaurant_images || []}
                        onSaveKeys={handleSaveRestaurantImages}
                    />
                </div>
            )}

            {/* Hide Orders when Menu is open to avoid clutter? Or keep both? Let's hide orders if Menu is strictly overlay mode, but here it's inline. Let's keep orders visible below for context or hide them if showMenu is true to focus. */}
            {/* Let's hide stats and board if showMenu is true for cleaner focus */}

            {!showMenu && !showImages && (
                <>
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
                </>
            )}
        </div>
    )
}
