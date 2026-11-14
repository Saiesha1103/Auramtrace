import { useState } from 'react';
import { Logo } from '../../components/Nav';
import { Icon } from '../../components/Icon';
import { login } from '../data/api';
import { syncWithBackend } from '../data/store';

interface LoginProps {
  onSuccess?: () => void;
  onExploreDemo?: () => void;
}

export function Login({ onSuccess, onExploreDemo }: LoginProps) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!email.trim() || !password) {
      setError('Please enter both your email address and password.');
      return;
    }

    setLoading(true);
    try {
      const res = await login(email.trim(), password);
      if (res.ok) {
        await syncWithBackend();
        onSuccess?.();
      } else {
        setError(res.error || 'Authentication failed. Please verify your credentials.');
      }
    } catch (err: any) {
      setError(err.message || 'Connection to authentication service failed.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-wrap">
      <div className="login-card">
        <div className="login-brand">
          <Logo />
        </div>

        <div className="login-header">
          <h1 className="login-title">Vault Sign In</h1>
          <p className="login-subtitle">
            Sign in to access your organisation's authoritative bullion ledger & manufacturing intelligence.
          </p>
        </div>

        {error && (
          <div className="login-alert" role="alert">
            <Icon name="alert" size={16} />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="login-form">
          <div className="login-field">
            <label htmlFor="auth-email">Email Address</label>
            <div className="login-input-wrap">
              <input
                id="auth-email"
                type="email"
                autoComplete="email"
                required
                placeholder="name@company.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={loading}
                autoFocus
              />
            </div>
          </div>

          <div className="login-field">
            <label htmlFor="auth-password">Password</label>
            <div className="login-input-wrap">
              <input
                id="auth-password"
                type="password"
                autoComplete="current-password"
                required
                placeholder="••••••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={loading}
              />
            </div>
          </div>

          <button
            type="submit"
            className="btn btn-gold login-submit"
            disabled={loading}
          >
            {loading ? (
              <>
                <span className="login-spinner" aria-hidden="true" />
                <span>Authenticating…</span>
              </>
            ) : (
              <>
                <Icon name="check" size={16} />
                <span>Sign In to Vault</span>
              </>
            )}
          </button>
        </form>

        <div className="login-divider">
          <span>or</span>
        </div>

        <div className="login-actions">
          {onExploreDemo && (
            <button
              type="button"
              className="btn btn-ghost login-demo-btn"
              onClick={onExploreDemo}
              disabled={loading}
            >
              <span>Explore Offline Demo Mode</span>
            </button>
          )}

          <a href="#top" className="login-back-link">
            ← Back to Public Website
          </a>
        </div>
      </div>
    </div>
  );
}
