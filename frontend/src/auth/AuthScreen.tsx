import { Button, StateMessage } from '../components/ui';

export function AuthScreen({ error, signingIn, onSignIn }: { error: string | null; signingIn: boolean; onSignIn: () => void }) {
  return (
    <main className="grid min-h-svh place-items-center bg-background px-6">
      <section className="w-full max-w-md">
        <div className="grid gap-8">
          <div className="text-4xl font-semibold tracking-tight">iris</div>
          {error && <StateMessage tone="error">{error}</StateMessage>}
          <Button
            className="h-auto justify-between px-0 py-3 text-base"
            uiVariant="plainIcon"
            type="button"
            onClick={onSignIn}
            disabled={signingIn}
          >
            <span>The good web is still out there</span>
            <span aria-hidden="true">→</span>
          </Button>
        </div>
      </section>
    </main>
  );
}
