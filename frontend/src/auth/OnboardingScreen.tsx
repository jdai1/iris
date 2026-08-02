import { FormEvent, useState } from 'react';
import { ArrowRight, Globe2 } from 'lucide-react';
import { completeOnboarding } from '../api';
import { IrisMark } from '../components/IrisMark';
import { Button, StateMessage } from '../components/ui';
import type { User } from '../types';

export function OnboardingScreen({ user, onComplete }: { user: User; onComplete: (user: User) => void }) {
  const [username, setUsername] = useState(user.username ?? suggestedUsername(user.email));
  const [websiteUrl, setWebsiteUrl] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!username.trim() || saving) return;
    setSaving(true);
    setError(null);
    try {
      const completedUser = await completeOnboarding({
        username: username.trim(),
        website_url: websiteUrl.trim() || null,
      });
      window.history.replaceState(null, '', '/search');
      onComplete(completedUser);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not finish setup');
    } finally {
      setSaving(false);
    }
  }

  return (
    <main className="grid min-h-svh place-items-center bg-background px-6 py-12">
      <section className="w-full max-w-xl">
        <div className="mb-10 inline-flex items-center gap-2 text-sm font-semibold text-muted-foreground">
          <IrisMark className="size-6" />
          <span>iris</span>
        </div>

        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Welcome to Iris</span>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight">Choose how you’ll appear</h1>
        <p className="mt-2 max-w-md text-sm leading-6 text-muted-foreground">
          Your profile stays private to your connections. You can change these details later.
        </p>

        <form className="mt-8 grid gap-6" onSubmit={submit}>
          {error && <StateMessage tone="error">{error}</StateMessage>}

          <label className="grid gap-2">
            <span className="text-sm font-medium">Username</span>
            <div className="flex h-11 items-center rounded-md border bg-background px-3 focus-within:ring-2 focus-within:ring-ring/30">
              <span className="mr-1 text-sm text-muted-foreground">@</span>
              <input
                className="min-w-0 flex-1 bg-transparent text-sm outline-none"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                autoComplete="username"
                autoFocus
                aria-label="Username"
              />
            </div>
          </label>

          <label className="grid gap-2">
            <span className="flex items-center justify-between gap-3 text-sm font-medium">
              <span>Personal website</span>
              <small className="font-normal text-muted-foreground">Optional</small>
            </span>
            <div className="flex h-11 items-center gap-2 rounded-md border bg-background px-3 focus-within:ring-2 focus-within:ring-ring/30">
              <Globe2 className="size-4 shrink-0 text-muted-foreground" />
              <input
                className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
                value={websiteUrl}
                onChange={(event) => setWebsiteUrl(event.target.value)}
                placeholder="https://yoursite.com"
                inputMode="url"
                aria-label="Personal website URL"
              />
            </div>
          </label>

          <Button className="w-fit" uiVariant="solid" type="submit" disabled={saving || !username.trim()}>
            {saving ? 'Setting up…' : 'Continue'}
            {!saving && <ArrowRight size={15} />}
          </Button>
        </form>
      </section>
    </main>
  );
}

function suggestedUsername(email: string) {
  return email.split('@')[0]?.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || '';
}
