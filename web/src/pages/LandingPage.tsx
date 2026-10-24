import { Link } from 'react-router-dom'
import { Container, Heading, SignInLink } from '../components/ui'
import { BrandMark, HandIcon, CoinIcon, BalanceIcon, CheckIcon } from '../components/icons'

const principles = [
  { title: 'Voluntary', copy: 'Buildings always choose whether to participate.', icon: HandIcon },
  { title: 'Paid', copy: 'Participants are compensated for every approved event.', icon: CoinIcon },
  { title: 'Equity-constrained', copy: 'Built-in limits distribute requests more fairly.', icon: BalanceIcon },
  { title: 'Human-approved', copy: 'An operator reviews every event before it begins.', icon: CheckIcon },
]

const steps = [
  { number: '01', text: 'Utilities ask buildings to reduce load during periods of grid stress.' },
  { number: '02', text: 'Buildings opt in to event participation and get paid.' },
  { number: '03', text: 'An equity cap helps prevent the same neighborhoods from being asked repeatedly.' },
  { number: '04', text: 'A human operator reviews and approves every event.' },
]

export function LandingPage() {
  return (
    <div className="site-shell">
      <header className="site-header">
        <Container className="nav">
          <Link className="brand" to="/" aria-label="Commonwatt home">
            <BrandMark className="brand-mark" />
            <span>Commonwatt</span>
          </Link>
          <SignInLink quiet />
        </Container>
      </header>
      <main>
        <section className="hero" aria-labelledby="hero-heading">
          <Container>
            <div className="eyebrow">
              <span className="eyebrow-dot" />
              Built for Massachusetts utilities
            </div>
            <Heading level={1} id="hero-heading">
              Keep the grid up without leaning on the same neighborhoods twice.
            </Heading>
            <p className="hero-copy">
              Commonwatt helps utilities plan voluntary, paid demand-response events while making
              equity a requirement—not an afterthought.
            </p>
            <SignInLink />
          </Container>
          <div className="hero-rule" aria-hidden="true">
            <span />
          </div>
        </section>

        <section className="principles" aria-labelledby="principles-heading">
          <Container>
            <div className="section-intro">
              <p className="kicker">A fairer operating model</p>
              <Heading level={2} id="principles-heading">
                Designed around public trust.
              </Heading>
            </div>
            <div className="card-grid">
              {principles.map(({ title, copy, icon: Icon }) => (
                <article className="principle-card" key={title}>
                  <div className="icon-wrap">
                    <Icon className="icon" />
                  </div>
                  <Heading level={3}>{title}</Heading>
                  <p>{copy}</p>
                </article>
              ))}
            </div>
          </Container>
        </section>

        <section className="process" aria-labelledby="process-heading">
          <Container>
            <div className="process-heading">
              <p className="kicker">How it works</p>
              <Heading level={2} id="process-heading">
                From grid need to approved event.
              </Heading>
            </div>
            <ol className="steps">
              {steps.map((step) => (
                <li key={step.number}>
                  <span className="step-number">{step.number}</span>
                  <p>{step.text}</p>
                </li>
              ))}
            </ol>
          </Container>
        </section>
      </main>
      <footer>
        <Container className="footer-inner">
          <div className="footer-brand">
            <BrandMark className="footer-mark" />
            <span>Commonwatt</span>
          </div>
          <p>Equitable demand response for a more resilient grid.</p>
          <SignInLink quiet />
        </Container>
      </footer>
    </div>
  )
}
