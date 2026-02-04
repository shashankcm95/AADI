import { useState, useEffect } from 'react'
import { signInWithRedirect, signOut, getCurrentUser, fetchAuthSession } from 'aws-amplify/auth'
import './App.css'

function App() {
  const [user, setUser] = useState(null)
  const [token, setToken] = useState(null)
  const [apiResponse, setApiResponse] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    checkUser()
  }, [])

  async function checkUser() {
    try {
      const currentUser = await getCurrentUser()
      setUser(currentUser)
      const session = await fetchAuthSession()
      const idToken = session.tokens?.idToken?.toString()
      setToken(idToken)
    } catch (err) {
      console.log('Not signed in')
      setUser(null)
      setToken(null)
    }
    setLoading(false)
  }

  async function handleSignIn() {
    try {
      await signInWithRedirect({ provider: 'Google' })
    } catch (err) {
      console.error('Sign in error:', err)
    }
  }

  async function handleSignOut() {
    try {
      await signOut()
      setUser(null)
      setToken(null)
    } catch (err) {
      console.error('Sign out error:', err)
    }
  }

  async function testHealthEndpoint() {
    setApiResponse({ loading: true })
    try {
      const res = await fetch('https://f7mqfaxh8i.execute-api.us-east-1.amazonaws.com/v1/health')
      const data = await res.json()
      setApiResponse({ status: res.status, data })
    } catch (err) {
      setApiResponse({ error: err.message })
    }
  }

  async function testProtectedEndpoint() {
    if (!token) {
      setApiResponse({ error: 'No token available. Please sign in.' })
      return
    }
    setApiResponse({ loading: true })
    try {
      const res = await fetch('https://f7mqfaxh8i.execute-api.us-east-1.amazonaws.com/v1/orders', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          restaurant_id: 'rst_001',
          items: [{ id: 'item_burger', quantity: 1 }],
        }),
      })
      const data = await res.json()
      setApiResponse({ status: res.status, data })
    } catch (err) {
      setApiResponse({ error: err.message })
    }
  }

  if (loading) {
    return <div className="container"><p>Loading...</p></div>
  }

  return (
    <div className="container">
      <header>
        <h1>🍔 Arrive API Test Client</h1>
      </header>

      <section className="auth-section">
        {user ? (
          <div className="user-info">
            <p>✅ Signed in as: <strong>{user.username}</strong></p>
            <button onClick={handleSignOut} className="btn btn-danger">Sign Out</button>
          </div>
        ) : (
          <div className="sign-in-prompt">
            <p>Please sign in to test authenticated endpoints.</p>
            <button onClick={handleSignIn} className="btn btn-primary">
              🔐 Sign in with Google
            </button>
          </div>
        )}
      </section>

      {token && (
        <section className="token-section">
          <h3>🎫 ID Token (first 50 chars):</h3>
          <code>{token.substring(0, 50)}...</code>
        </section>
      )}

      <section className="test-section">
        <h2>API Tests</h2>
        <div className="button-group">
          <button onClick={testHealthEndpoint} className="btn">
            🏥 Test Health (Public)
          </button>
          <button onClick={testProtectedEndpoint} className="btn" disabled={!user}>
            📦 Create Order (Protected)
          </button>
        </div>
      </section>

      {apiResponse && (
        <section className="response-section">
          <h3>Response:</h3>
          {apiResponse.loading ? (
            <p>Loading...</p>
          ) : (
            <pre>{JSON.stringify(apiResponse, null, 2)}</pre>
          )}
        </section>
      )}
    </div>
  )
}

export default App
