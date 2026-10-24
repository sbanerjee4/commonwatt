import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Heading } from '../components/ui'
import { BrandMark, ArrowIcon } from '../components/icons'
import { login } from '../lib/session'

// Real credential sign-in against the backend /auth/login (cookie session).
// Demo accounts live in db/seed.py:
//   utility@demo / demo-utility-pass        (operator)
//   building1@demo / demo-building-pass      (facility manager)
export function SignInPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const navigate = useNavigate()

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault()
    setError(null)
    setBusy(true)
    try {
      const identity = await login(email.trim(), password)
      navigate(identity.role === 'utility' ? '/utility' : '/building')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sign-in failed.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="auth-page">
      <div className="auth-card">
        <Link className="brand auth-brand" to="/" aria-label="Commonwatt home">
          <BrandMark className="brand-mark" />
          <span>Commonwatt</span>
        </Link>
        <div className="auth-heading">
          <Heading level={1}>Welcome back.</Heading>
          <p>Sign in with your Commonwatt account.</p>
        </div>
        <form className="auth-form" onSubmit={onSubmit}>
          <label>
            Email address
            <input
              type="text"
              placeholder="name@organization.org"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </label>
          <label>
            Password
            <input
              type="password"
              placeholder="Enter your password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </label>
          {error && (
            <p className="auth-error" role="alert">
              {error}
            </p>
          )}
          <button type="submit" className="button auth-submit" disabled={busy}>
            {busy ? 'Signing in…' : 'Sign in'}
            <ArrowIcon className="button-icon" />
          </button>
        </form>
        <Link to="/" className="back-link">
          ← Back to public page
        </Link>
      </div>
    </main>
  )
}
