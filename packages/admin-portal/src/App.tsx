import { Authenticator } from '@aws-amplify/ui-react'
import '@aws-amplify/ui-react/styles.css'
import './App.css'
import Dashboard from './components/Dashboard'

function AdminAuthHeader() {
  return (
    <div className="auth-brand-header">
      <img src="/logo_icon_stylized.png" alt="AADI logo" className="auth-brand-logo" />
      <div>
        <h2>AADI</h2>
        <p>Admin Portal</p>
      </div>
    </div>
  )
}

const authComponents = {
  Header: AdminAuthHeader,
}

function App() {
  return (
    <Authenticator className="admin-auth-shell" hideSignUp={true} components={authComponents}>
      {({ user, signOut }) => (
        <Dashboard user={user} signOut={signOut} />
      )}
    </Authenticator>
  )
}

export default App
