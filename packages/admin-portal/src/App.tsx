import { Authenticator } from '@aws-amplify/ui-react'
import '@aws-amplify/ui-react/styles.css'
import './App.css'
import Dashboard from './components/Dashboard'

function App() {
  return (
    <Authenticator hideSignUp={true}>
      {({ user, signOut }) => (
        <Dashboard user={user} signOut={signOut} />
      )}
    </Authenticator>
  )
}

export default App
