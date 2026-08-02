import { ArrowRight } from 'lucide-react';
import { Button, StateMessage } from '../components/ui';
import { IrisMark } from '../components/IrisMark';

export function AuthScreen({ error, signingIn, onSignIn }: { error: string | null; signingIn: boolean; onSignIn: () => void }) {
  return (
    <main className="grid min-h-svh items-start overflow-auto bg-background px-[clamp(2rem,7vw,7rem)] py-16 sm:items-center sm:py-0">
      <section className="grid w-full max-w-[57.5rem] sm:-translate-y-[2vh]">
        <div className="grid gap-5">
          <div className="inline-flex items-center gap-2 text-sm font-semibold text-muted-foreground">
            <IrisMark className="size-6" />
            <span>iris</span>
          </div>
          {error && <StateMessage tone="error">{error}</StateMessage>}
          <Button
            className="group h-auto w-fit max-w-full justify-start gap-3.5 rounded-none px-0 py-0 text-left text-[clamp(1.875rem,3.7vw,3.375rem)] font-bold leading-[1.08] whitespace-normal hover:text-foreground sm:whitespace-nowrap"
            uiVariant="plainIcon"
            type="button"
            onClick={onSignIn}
            disabled={signingIn}
            aria-label={signingIn ? 'Signing in with Google' : 'Continue with Google'}
          >
            <span className="decoration-2 underline-offset-[0.18em] group-hover:underline">
              {signingIn ? 'Opening Google sign-in…' : 'The good web is still out there'}
            </span>
            <ArrowRight className="size-[0.72em] transition-transform group-hover:translate-x-1" aria-hidden="true" />
          </Button>
        </div>
      </section>
    </main>
  );
}
