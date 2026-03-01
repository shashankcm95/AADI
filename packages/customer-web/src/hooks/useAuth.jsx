import { useState, useEffect, useCallback } from 'react'
import { fetchAuthSession } from 'aws-amplify/auth'

/**
 * Custom hook for auth token management.
 * Fetches the Cognito ID token, enforces RBAC (blocks admin roles),
 * and provides a stable token value for API calls.
 */
export function useAuth(signOut) {
    const [token, setToken] = useState(null)
    const [loading, setLoading] = useState(true)

    const fetchToken = useCallback(async () => {
        try {
            const session = await fetchAuthSession()
            const idToken = session.tokens?.idToken
            const payload = idToken?.payload || {}

            // RBAC Check: Block Restaurant/Super Admins
            const role = payload['custom:role']
            if (role === 'admin' || role === 'restaurant_admin') {
                console.warn('Access Denied: admin/restaurant_admin roles must use the Administrator Portal.')
                signOut()
                return
            }

            setToken(idToken?.toString())
        } catch (err) {
            console.log('Not signed in', err)
            setToken(null)
        }
        setLoading(false)
    }, [signOut])

    useEffect(() => {
        fetchToken()
    }, [fetchToken])

    return { token, loading }
}
