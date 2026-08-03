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
    <div className="fixed inset-0 z-[100] grid place-items-center bg-black/20 px-5 py-8 backdrop-blur-[2px]">
      <section className="w-full max-w-lg rounded-lg border bg-background p-6 shadow-2xl" role="dialog" aria-modal="true" aria-labelledby="onboarding-title">
        <div className="inline-flex items-center gap-2 text-sm font-semibold text-muted-foreground">
          <IrisMark className="size-5" />
          <span>iris</span>
        </div>

        <h1 className="mt-6 text-xl font-semibold tracking-tight" id="onboarding-title">Set up your profile</h1>
        <p className="mt-1.5 max-w-md text-sm leading-6 text-muted-foreground">
          Only your connections can see it.
        </p>

        <form className="mt-6 grid gap-5" onSubmit={submit}>
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
            <span className="text-sm font-medium">Personal website</span>
            <div className="flex h-11 items-center gap-2 rounded-md border bg-background px-3 focus-within:ring-2 focus-within:ring-ring/30">
              <Globe2 className="size-4 shrink-0 text-muted-foreground" />
              <input
                className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
                value={websiteUrl}
                onChange={(event) => setWebsiteUrl(event.target.value)}
                placeholder="https://yoursite.com (optional)"
                inputMode="url"
                aria-label="Personal website URL"
              />
            </div>
          </label>

          <Button className="ml-auto w-fit" uiVariant="solid" type="submit" disabled={saving || !username.trim()}>
            {saving ? 'Setting up…' : 'Continue'}
            {!saving && <ArrowRight size={15} />}
          </Button>
        </form>
      </section>
    </div>
  );
}

function suggestedUsername(email: string) {
  return email.split('@')[0]?.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || '';
}
