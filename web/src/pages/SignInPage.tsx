import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Heading } from '../components/ui'
import { BrandMark, ArrowIcon } from '../components/icons'

// NOTE: the BFF does not expose /auth/* yet (see bff/app.py), so this page is a
// UI shell that routes by selected role. Real authentication wires in once the
// auth endpoints land.
export function SignInPage() {
  const [role, setRole] = useState<'utility' | 'facility'>('facility')
  const navigate = useNavigate()

  function onSubmit(event: React.FormEvent) {
    event.preventDefault()
    navigate(role === 'utility' ? '/utility' : '/building')
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
          <p>Choose your account type to access the right Commonwatt workspace.</p>
        </div>
        <div className="role-toggle" role="group" aria-label="Account type">
          {(['utility', 'facility'] as const).map((item) => (
            <button
              type="button"
              key={item}
              className={role === item ? 'role-option selected' : 'role-option'}
              onClick={() => setRole(item)}
              aria-pressed={role === item}
            >
              <span className="radio-mark" />
              {item === 'utility' ? 'Utility' : 'Facility manager'}
              {role === item && <span className="selected-label">Selected</span>}
            </button>
          ))}
        </div>
        <form className="auth-form" onSubmit={onSubmit}>
          <label>
            Email address
            <input type="email" placeholder="name@organization.org" autoComplete="email" />
          </label>
          <label>
            Password
            <input type="password" placeholder="Enter your password" autoComplete="current-password" />
          </label>
          <button type="submit" className="button auth-submit">
            Sign in
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
