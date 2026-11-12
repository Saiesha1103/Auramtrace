import { useEffect, useState } from 'react';
import { Button } from './Button';
import { scrollToId } from '../lib/useSmoothScroll';
import './Nav.css';

const LINKS = [
  { id: 'platform', label: 'Platform' },
  { id: 'journey', label: 'Gold Journey' },
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'investigation', label: 'AI Investigation' },
];

export function Logo() {
  return (
    <span className="logo">
      <svg className="logo-mark" viewBox="0 0 40 40" aria-hidden="true">
        <defs>
          <linearGradient id="logo-g" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#fbeec6" />
            <stop offset=".5" stopColor="#e2b35c" />
            <stop offset="1" stopColor="#9a6424" />
          </linearGradient>
        </defs>
        <path d="M20 3 4 37h5.6L20 14.2 30.4 37H36L20 3Z" fill="url(#logo-g)" />
        <path d="M13.4 37 20 22.6 26.6 37h-4l-2.6-5.8-2.6 5.8h-4Z" fill="url(#logo-g)" opacity=".55" />
      </svg>
      <span className="logo-word">AURUMTRACE</span>
    </span>
  );
}

export function Nav() {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const on = () => setScrolled(window.scrollY > 24);
    on();
    window.addEventListener('scroll', on, { passive: true });
    return () => window.removeEventListener('scroll', on);
  }, []);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false);
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  const go = (id: string) => (e: React.MouseEvent) => {
    e.preventDefault();
    setOpen(false);
    scrollToId(id);
  };

  return (
    <header className={`nav ${scrolled ? 'is-scrolled' : ''} ${open ? 'is-open' : ''}`}>
      <div className="nav-inner container">
        <a href="#top" className="nav-brand" onClick={go('top')} aria-label="AURUMTRACE home">
          <Logo />
          <span className="nav-tagline" aria-hidden="true">
            Precious-metal
            <br />
            intelligence platform
          </span>
        </a>

        <nav className="nav-links" aria-label="Primary">
          {LINKS.map((l) => (
            <a key={l.id} href={`#${l.id}`} onClick={go(l.id)}>
              {l.label}
            </a>
          ))}
        </nav>

        <div className="nav-actions">
          <Button variant="ghost" href="#/app/dashboard" className="nav-login">
            Log In
          </Button>
          <Button href="#cta" icon="arrow" className="nav-start">
            Get Started
          </Button>
          <button
            className="nav-burger"
            aria-label={open ? 'Close menu' : 'Open menu'}
            aria-expanded={open}
            aria-controls="mobile-menu"
            onClick={() => setOpen((o) => !o)}
          >
            <span />
            <span />
          </button>
        </div>
      </div>

      <div id="mobile-menu" className="nav-sheet" hidden={!open}>
        {LINKS.map((l) => (
          <a key={l.id} href={`#${l.id}`} onClick={go(l.id)}>
            {l.label}
          </a>
        ))}
        <Button href="#cta" icon="arrow" size="lg" onClick={() => setOpen(false)}>
          Get Started
        </Button>
      </div>
    </header>
  );
}
