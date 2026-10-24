import { createElement } from 'react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { BrandMark, ArrowIcon } from './icons'

export function Container({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`container ${className}`.trim()}>{children}</div>
}

export function Heading({
  level,
  id,
  className,
  children,
}: {
  level: 1 | 2 | 3
  id?: string
  className?: string
  children: ReactNode
}) {
  return createElement(`h${level}`, { id, className }, children)
}

export function Tag({ children, tone = '' }: { children: ReactNode; tone?: string }) {
  return <span className={`tag ${tone}`.trim()}>{children}</span>
}

export function Panel({
  title,
  tools,
  className = '',
  children,
}: {
  title: string
  tools?: ReactNode
  className?: string
  children: ReactNode
}) {
  return (
    <section className={`panel ${className}`.trim()}>
      <div className="panel-head">
        <Heading level={2}>{title}</Heading>
        {tools}
      </div>
      {children}
    </section>
  )
}

export function SignInLink({ quiet = false }: { quiet?: boolean }) {
  return (
    <Link className={quiet ? 'text-link' : 'button'} to="/signin">
      Sign in
      {!quiet && <ArrowIcon className="button-icon" />}
    </Link>
  )
}

export function AppHeader({ context }: { context?: string }) {
  return (
    <header className="app-header">
      <Link className="brand" to="/" aria-label="Commonwatt home">
        <BrandMark className="brand-mark" />
        <span>Commonwatt</span>
      </Link>
      <div className="app-identity">
        {context && <span className="role-label">{context}</span>}
        <Link to="/" className="text-link">
          Sign out
        </Link>
      </div>
    </header>
  )
}
