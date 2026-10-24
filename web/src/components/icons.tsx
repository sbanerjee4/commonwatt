import type { SVGProps } from 'react'

type IconProps = SVGProps<SVGSVGElement>

export function BrandMark({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 40 40" fill="none" aria-hidden="true">
      <path d="M8 13.5 20 7l12 6.5v13L20 33 8 26.5v-13Z" stroke="currentColor" strokeWidth="2" />
      <path d="m13 23 5-6 4 5 5-6" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function HandIcon(props: IconProps) {
  return (
    <svg {...props} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M7 11.5V8a1.5 1.5 0 0 1 3 0v2-4a1.5 1.5 0 0 1 3 0v4-3a1.5 1.5 0 0 1 3 0v4-2a1.5 1.5 0 0 1 3 0v5.5c0 4.1-2.7 6.5-6.5 6.5h-1.1a6 6 0 0 1-4.2-1.8l-3.8-3.9a1.8 1.8 0 0 1 2.5-2.6L7 13.8" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function CoinIcon(props: IconProps) {
  return (
    <svg {...props} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="8.5" stroke="currentColor" strokeWidth="1.7" />
      <path d="M14.7 8.6c-.7-.5-1.5-.8-2.5-.8-1.4 0-2.5.7-2.5 1.8 0 2.8 5.1 1.3 5.1 4.4 0 1.2-1 2.1-2.8 2.1-1 0-2-.3-2.8-1M12 6.3v1.5m0 8.3v1.6" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  )
}

export function BalanceIcon(props: IconProps) {
  return (
    <svg {...props} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M12 4v16M7 20h10M5 7h14M7 7l-3 6h6L7 7Zm10 0-3 6h6l-3-6Z" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function CheckIcon(props: IconProps) {
  return (
    <svg {...props} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M8.2 12.4 10.7 15l5.5-6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="12" cy="12" r="8.5" stroke="currentColor" strokeWidth="1.7" />
    </svg>
  )
}

export function ArrowIcon(props: IconProps) {
  return (
    <svg {...props} viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="M4 10h11m-4-4 4 4-4 4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}
