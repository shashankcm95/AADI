import { useState, useEffect, useCallback, useRef } from 'react'
import { fetchAuthSession, fetchUserAttributes } from 'aws-amplify/auth'
import { Restaurant, MenuItem, Order } from '../types'
import * as api from '../services/api'
import '../App.css'
import StatsBar from './StatsBar'
import KanbanBoard from './KanbanBoard'
import RestaurantForm from './RestaurantForm'
import AdminDashboard from './AdminDashboard'
import MenuIngestion from './MenuIngestion'
import CapacitySettings from './CapacitySettings'
import RestaurantImageManager from './RestaurantImageManager'
import PosSettings from './PosSettings'

// TODO(PKG-007): Auto-promotion should be server-side (e.g. Step Functions or EventBridge
// scheduled rule). Client-side setTimeout is unreliable — the browser tab may be closed,
// backgrounded, or the user may not have the dashboard open. See packages/BACKLOG.md.
const AUTO_PROMOTE_DELAY_MS = 2 * 60 * 1000
const COMPLETED_LANE_LIMIT = 20

interface DashboardProps {
    user: { username?: string } | undefined;
    signOut: (() => void) | undefined;
}

export default function Dashboard({ user, signOut }: DashboardProps) {
    // --- STATE ---
    const [isAuthenticated, setIsAuthenticated] = useState(false)
    const [restaurants, setRestaurants] = useState<Restaurant[]>([])
    const [selectedRestaurant, setSelectedRestaurant] = useState<string | null>(null)
    const [orders, setOrders] = useState<Order[]>([])
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)
    const [lastRefresh, setLastRefresh] = useState<string | null>(null)
    const [newOrderAlert, setNewOrderAlert] = useState(false)
    const [showAddRestaurant, setShowAddRestaurant] = useState(false)

    // Menu Management State
    const [showMenu, setShowMenu] = useState(false)
    const [menuItems, setMenuItems] = useState<MenuItem[]>([])

    // Capacity Management State
    const [showCapacity, setShowCapacity] = useState(false)
    const [showArchived, setShowArchived] = useState(false)
    const [showImages, setShowImages] = useState(false)
    const [showPosSettings, setShowPosSettings] = useState(false)
    const [orderActionState, setOrderActionState] = useState<Record<string, boolean>>({})

    const prevOrderIds = useRef<Set<string>>(new Set())
    const autoTransitionInFlight = useRef<Set<string>>(new Set())
    const incomingSeenAt = useRef<Map<string, number>>(new Map())

    // RBAC State
    const [assignedRestaurantId, setAssignedRestaurantId] = useState<string | null>(null)
    const [isAdmin, setIsAdmin] = useState(false)

    useEffect(() => {
        checkUser()
    }, [])

    async function checkUser() {
        try {
            const session = await fetchAuthSession()
            const idToken = session.tokens?.idToken?.toString() ?? null
            if (!idToken) {
                setLoading(false)
                return
            }

            // RBAC Check — resolve all auth state before setting isAuthenticated to prevent
            // the useEffect from firing fetchRestaurants prematurely.
            const attrs = await fetchUserAttributes()
            const role = attrs['custom:role']
            const RestId = attrs['custom:restaurant_id']

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
                // Access denied or customer — fires once before sign-out
                console.error("Access Denied: Unknown Role", role)
                setLoading(false)
                alert("Access Denied: Customers cannot access the Admin Portal.")
                if (signOut) signOut()
                return
            }

            // Set authenticated last so the useEffect fires only after role/restaurant
            // state is already committed, avoiding a race in fetchRestaurants.
            setIsAuthenticated(true)

        } catch (err) {
            console.error(err)
            setIsAuthenticated(false)
        }
        setLoading(false)
    }

    // Fetch restaurants when authenticated
    useEffect(() => {
        if (isAuthenticated) {
            fetchRestaurants()
        }
    }, [isAuthenticated])

    async function fetchRestaurants() {
        try {
            const rests = await api.fetchRestaurants()
            setRestaurants(rests)

            // For restaurant_admin, selectedRestaurant is already set in checkUser.
            // But we want to ensure we have the NAME from the list.
            if (rests.length > 0 && !selectedRestaurant) {
                setSelectedRestaurant(rests[0].restaurant_id)
            }
        } catch (err) {
            console.error('Failed to fetch restaurants:', err)
        }
    }

    // Auto-Activation: Run when we have BOTH the restaurant list and the assigned ID
    useEffect(() => {
        if (assignedRestaurantId && restaurants.length > 0) {
            const myRestaurant = restaurants.find(r => r.restaurant_id === assignedRestaurantId)
            if (myRestaurant && !myRestaurant.active) {

                activateRestaurant(assignedRestaurantId)
            }
        }
    }, [assignedRestaurantId, restaurants])

    async function activateRestaurant(id: string) {
        try {
            await api.updateRestaurant(id, { active: true })
            fetchRestaurants()
        } catch (e) {
            console.error("Failed to activate restaurant:", e)
        }
    }

    const fetchOrders = useCallback(async () => {
        if (!isAuthenticated || !selectedRestaurant) return
        setError(null)

        try {
            const fetchedOrders = await api.fetchOrders(selectedRestaurant)

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

            const incomingOrders = fetchedOrders
                .filter((o: Order) => o.status === 'SENT_TO_DESTINATION')
            const incomingNow = new Set<string>()
            const nowMs = Date.now()

            for (const incoming of incomingOrders) {
                incomingNow.add(incoming.order_id)
                if (!incomingSeenAt.current.has(incoming.order_id)) {
                    const persistedAtMs = typeof incoming.updated_at === 'number'
                        ? incoming.updated_at * 1000
                        : (typeof incoming.created_at === 'number' ? incoming.created_at * 1000 : nowMs)
                    incomingSeenAt.current.set(incoming.order_id, persistedAtMs)
                }
            }

            for (const trackedOrderId of incomingSeenAt.current.keys()) {
                if (!incomingNow.has(trackedOrderId)) {
                    incomingSeenAt.current.delete(trackedOrderId)
                }
            }

            const autoAdvanceIds = incomingOrders
                .map((o: Order) => o.order_id)
                .filter((orderId: string) => !autoTransitionInFlight.current.has(orderId))
                .filter((orderId: string) => {
                    const seenAt = incomingSeenAt.current.get(orderId)
                    if (!seenAt) return false
                    return nowMs - seenAt >= AUTO_PROMOTE_DELAY_MS
                })

            for (const orderId of autoAdvanceIds) {
                autoTransitionInFlight.current.add(orderId)
                void autoPromoteIncomingOrder(orderId)
            }
        } catch (err: unknown) {
            setError(err instanceof Error ? err.message : 'Failed to fetch orders')
        }
    }, [isAuthenticated, selectedRestaurant])

    const fetchMenu = useCallback(async () => {
        if (!isAuthenticated || !selectedRestaurant) return
        try {
            const items = await api.fetchMenu(selectedRestaurant)
            setMenuItems(items)
        } catch (e) {
            console.error("Failed to fetch menu:", e)
            setMenuItems([])
        }
    }, [isAuthenticated, selectedRestaurant])

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
                try {
                    oscillator.stop()
                } finally {
                    audioContext.close()
                }
            }, 200)
        } catch (e) {
            console.warn('Audio not supported:', e)
        }
    }

    async function handleSaveRestaurantImages(keys: string[]) {
        if (!isAuthenticated || !selectedRestaurant) return
        await api.updateRestaurant(selectedRestaurant, { restaurant_image_keys: keys })
        await fetchRestaurants()
    }

    // Fetch orders and start polling when authenticated and restaurant is selected.
    // showMenu/fetchMenu are intentionally excluded: toggling the menu panel must
    // not reset order-tracking state or restart the polling interval.
    useEffect(() => {
        if (isAuthenticated && selectedRestaurant) {
            prevOrderIds.current = new Set()
            incomingSeenAt.current.clear()
            autoTransitionInFlight.current.clear()
            fetchOrders()

            const interval = setInterval(fetchOrders, 5000)
            return () => clearInterval(interval)
        }
    }, [isAuthenticated, selectedRestaurant, fetchOrders])

    // Fetch menu whenever the menu panel is opened.
    useEffect(() => {
        if (showMenu && isAuthenticated && selectedRestaurant) {
            fetchMenu()
        }
    }, [showMenu, isAuthenticated, selectedRestaurant, fetchMenu])


    function setOrderActionLoading(orderId: string, isLoading: boolean) {
        setOrderActionState((prev) => {
            if (isLoading) {
                return { ...prev, [orderId]: true }
            }
            const next = { ...prev }
            delete next[orderId]
            return next
        })
    }

    async function autoPromoteIncomingOrder(orderId: string) {
        if (!isAuthenticated || !selectedRestaurant) {
            autoTransitionInFlight.current.delete(orderId)
            return
        }
        try {
            // After timeout in Incoming, auto-ack first (best effort), then auto-start prep.
            try { await api.ackOrder(selectedRestaurant, orderId) } catch { /* best effort */ }
            await api.updateOrderStatus(selectedRestaurant, orderId, 'IN_PROGRESS')
        } catch (err) {
            console.warn(`Auto-promote error for order ${orderId}:`, err)
        } finally {
            autoTransitionInFlight.current.delete(orderId)
        }
    }

    async function postOrderStatus(orderId: string, newStatus: string) {
        if (!isAuthenticated || !selectedRestaurant) return
        await api.updateOrderStatus(selectedRestaurant, orderId, newStatus)
    }

    async function handleCompleteOrder(order: Order) {
        if (!isAuthenticated || !selectedRestaurant) return
        const completionPathByStatus: Record<string, string[]> = {
            IN_PROGRESS: ['READY', 'FULFILLING', 'COMPLETED'],
            READY: ['FULFILLING', 'COMPLETED'],
            FULFILLING: ['COMPLETED'],
        }
        const completionPath = completionPathByStatus[order.status]
        if (!completionPath || completionPath.length === 0) return

        setOrderActionLoading(order.order_id, true)
        try {
            for (const status of completionPath) {
                await postOrderStatus(order.order_id, status)
            }
            await fetchOrders()
        } catch (err: unknown) {
            setError(err instanceof Error ? err.message : 'Failed to complete order')
        } finally {
            setOrderActionLoading(order.order_id, false)
        }
    }

    function getOrderSortKey(order: Order) {
        return order.updated_at || order.created_at || 0
    }

    function getOrderItemsSummary(order: Order) {
        const orderItems = order.items && order.items.length > 0 ? order.items : (order.resources || [])
        if (orderItems.length === 0) return 'No items'
        return orderItems
            .map((item) => `${item.name || item.id || 'Item'} x${item.qty || 1}`)
            .join(', ')
    }

    function formatOrderDate(epoch?: number) {
        if (!epoch) return '—'
        return new Date(epoch * 1000).toLocaleString()
    }

    const completedOrders = [...orders]
        .filter((o) => o.status === 'COMPLETED')
        .sort((a, b) => getOrderSortKey(b) - getOrderSortKey(a))
    const recentCompletedOrders = completedOrders.slice(0, COMPLETED_LANE_LIMIT)
    const archivedOrders = completedOrders.slice(COMPLETED_LANE_LIMIT)
    const boardOrders = [
        ...orders.filter((o) => o.status !== 'COMPLETED'),
        ...recentCompletedOrders,
    ]

    // Counts
    const pendingCount = orders.filter(o => ['PENDING_NOT_SENT', 'WAITING_FOR_CAPACITY'].includes(o.status)).length
    const activeCount = orders.filter(o => ['IN_PROGRESS', 'READY', 'FULFILLING'].includes(o.status)).length
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
            <section className="restaurant-picker">
                <div className="restaurant-picker-main">
                    <label>📍 Managing Restaurant:</label>

                    {/* Only show picker if NOT assigned to a specific restaurant */}
                    {!assignedRestaurantId ? (
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
                        <span className="managed-restaurant-name">
                            {restaurants.find(r => r.restaurant_id === assignedRestaurantId)?.name || 'My Restaurant'}
                        </span>
                    )}

                    {/* Show Add Button if NOT restricted to a specific restaurant */}
                    {!assignedRestaurantId && (
                        <button
                            onClick={() => setShowAddRestaurant(true)}
                            className="btn btn-small btn-primary"
                        >
                            + Add Restaurant
                        </button>
                    )}

                    {selectedRestaurant && <span className="restaurant-id">ID: {selectedRestaurant}</span>}
                </div>

                {selectedRestaurant && (
                    <div className="restaurant-action-tabs">
                        <button
                            onClick={() => {
                                if (!showMenu) fetchMenu()
                                setShowMenu(prev => !prev)
                                setShowCapacity(false)
                                setShowArchived(false)
                                setShowImages(false)
                                setShowPosSettings(false)
                            }}
                            className={`btn btn-secondary peacock-tab ${showMenu ? 'active' : ''}`}
                        >
                            {showMenu ? 'Close Menu' : '📜 Manage Menu'}
                        </button>
                        <button
                            onClick={() => {
                                setShowArchived(prev => {
                                    const next = !prev
                                    if (next) {
                                        setShowMenu(false)
                                        setShowCapacity(false)
                                        setShowImages(false)
                                        setShowPosSettings(false)
                                    }
                                    return next
                                })
                            }}
                            className={`btn btn-secondary peacock-tab ${showArchived ? 'active' : ''}`}
                        >
                            {showArchived ? 'Close Archived' : `🗂️ Archived (${archivedOrders.length})`}
                        </button>
                        <button
                            onClick={() => {
                                setShowCapacity(true)
                                setShowMenu(false)
                                setShowArchived(false)
                                setShowImages(false)
                                setShowPosSettings(false)
                            }}
                            className={`btn btn-secondary peacock-tab ${showCapacity ? 'active' : ''}`}
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
                                        setShowArchived(false)
                                        setShowPosSettings(false)
                                    }
                                    return next
                                })
                            }}
                            className={`btn btn-secondary peacock-tab ${showImages ? 'active' : ''}`}
                        >
                            {showImages ? 'Close Images' : '🖼️ Images'}
                        </button>
                        <button
                            onClick={() => {
                                setShowPosSettings(prev => {
                                    const next = !prev
                                    if (next) {
                                        setShowMenu(false)
                                        setShowCapacity(false)
                                        setShowArchived(false)
                                        setShowImages(false)
                                    }
                                    return next
                                })
                            }}
                            className={`btn btn-secondary peacock-tab ${showPosSettings ? 'active' : ''}`}
                        >
                            {showPosSettings ? 'Close POS' : '🔌 POS'}
                        </button>
                    </div>
                )}
            </section>

            {showAddRestaurant && (
                <RestaurantForm
                    onSuccess={() => {
                        setShowAddRestaurant(false)
                        fetchRestaurants()
                    }}
                    onCancel={() => setShowAddRestaurant(false)}
                />
            )}

            {/* Menu Management View */}
            {showMenu && isAuthenticated && selectedRestaurant && (
                <div className="menu-management-section" style={{ marginBottom: '2rem' }}>
                    <MenuIngestion
                        restaurantId={selectedRestaurant}
                        onSuccess={fetchMenu}
                    />

                    <div className="menu-current-card">
                        <h3 className="menu-current-title">Current Menu ({menuItems.length} items)</h3>
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
                                                <td>${parseFloat(String(item.price))}</td>
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
            {showCapacity && isAuthenticated && selectedRestaurant && (
                <CapacitySettings
                    restaurantId={selectedRestaurant}
                    onClose={() => setShowCapacity(false)}
                />
            )}

            {showImages && isAuthenticated && selectedRestaurant && selectedRestaurantData && (
                <div style={{ marginBottom: '1.5rem' }}>
                    <RestaurantImageManager
                        restaurantId={selectedRestaurant}
                        initialImageKeys={selectedRestaurantData.restaurant_image_keys || []}
                        initialImageUrls={selectedRestaurantData.restaurant_images || []}
                        onSaveKeys={handleSaveRestaurantImages}
                    />
                </div>
            )}

            {showPosSettings && isAuthenticated && selectedRestaurant && (
                <PosSettings
                    restaurantId={selectedRestaurant}
                    onClose={() => setShowPosSettings(false)}
                />
            )}

            {showArchived && (
                <div className="menu-management-section" style={{ marginBottom: '2rem' }}>
                    <div className="menu-current-card">
                        <h3 className="menu-current-title">Archived Orders ({archivedOrders.length})</h3>
                        {archivedOrders.length === 0 ? (
                            <p>No archived orders yet.</p>
                        ) : (
                            <table className="admin-table">
                                <thead>
                                    <tr>
                                        <th>Order</th>
                                        <th>Customer</th>
                                        <th>Completed At</th>
                                        <th>Items</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {archivedOrders.map((order) => (
                                        <tr key={order.order_id}>
                                            <td>#{order.order_id.slice(-6)}</td>
                                            <td>{order.customer_name || 'Guest'}</td>
                                            <td>{formatOrderDate(order.updated_at || order.created_at)}</td>
                                            <td className="archived-items-cell">{getOrderItemsSummary(order)}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        )}
                    </div>
                </div>
            )}

            {!showMenu && !showImages && !showArchived && (
                <>
                    <StatsBar sentCount={sentCount} activeCount={activeCount} pendingCount={pendingCount} />

                    <div className="toolbar">
                        <button onClick={fetchOrders} className="btn">🔄 Refresh</button>
                        <span className="last-update">Last: {lastRefresh || 'Never'}</span>
                        {error && <span className="error">⚠️ {error}</span>}
                    </div>

                    {newOrderAlert && (
                        <div className="new-order-banner">
                            🔔 NEW ORDER RECEIVED!
                        </div>
                    )}

                    <KanbanBoard
                        orders={boardOrders}
                        loading={orders.length === 0 && !lastRefresh}
                        onCompleteOrder={handleCompleteOrder}
                        orderActionState={orderActionState}
                    />
                </>
            )}
        </div>
    )
}
