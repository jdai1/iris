import { StateMessage } from '../components/ui';

export function AuthScreen({ error, signingIn, onSignIn }: { error: string | null; signingIn: boolean; onSignIn: () => void }) {
  return (
    <main className="auth-shell">
      <section className="auth-landing">
        <div className="auth-content">
          <div className="auth-brand">
            <span>iris</span>
          </div>
          {error && <StateMessage className="error" tone="error">{error}</StateMessage>}
          <button className="auth-link-button" type="button" onClick={onSignIn} disabled={signingIn}>
            <span>The good web is still out there</span>
            <span aria-hidden="true">→</span>
          </button>
        </div>
      </section>
    </main>
  );
}
