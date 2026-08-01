import { FormEvent, useEffect, useState } from 'react';
import { ArrowUpRight, Globe2 } from 'lucide-react';
import {
  attachProfileWebsite,
  deleteProfileWebsite,
  getMyProfile,
  updateMyProfile,
} from '../api';
import { Button, ToastRegion, type ToastNotice } from '../components/ui';
import type { UserProfile } from '../types';

export function ProfileView({ onUsernameChange }: { onUsernameChange?: (username: string) => void }) {
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [username, setUsername] = useState('');
  const [websiteUrl, setWebsiteUrl] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<ToastNotice | null>(null);

  useEffect(() => {
    loadProfile();
  }, []);

  async function loadProfile() {
    setError(null);
    try {
      const nextProfile = await getMyProfile();
      setProfile(nextProfile);
      setUsername(nextProfile.username);
      onUsernameChange?.(nextProfile.username);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  async function saveUsername(event: FormEvent) {
    event.preventDefault();
    if (!username.trim() || username.trim() === profile?.username) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await updateMyProfile({ username: username.trim() });
      setProfile(updated);
      setUsername(updated.username);
      onUsernameChange?.(updated.username);
      setNotice({ id: Date.now(), title: 'Username saved', tone: 'success' });
    } catch (err) {
      setNotice({
        id: Date.now(),
        title: 'Could not save username',
        description: errorMessage(err),
        tone: 'error',
      });
    } finally {
      setBusy(false);
    }
  }

  async function addWebsite(event: FormEvent) {
    event.preventDefault();
    if (!websiteUrl.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await attachProfileWebsite({ url: websiteUrl.trim(), label: null });
      setWebsiteUrl('');
      await loadProfile();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function removeWebsite(websiteId: number) {
    setBusy(true);
    setError(null);
    try {
      await deleteProfileWebsite(websiteId);
      await loadProfile();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="mx-auto min-h-svh w-full max-w-3xl p-5 sm:p-8">
      <header className="mb-8">
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Settings</span>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">My profile</h1>
        <p className="mt-1 text-sm text-muted-foreground">Only connected friends can open your profile.</p>
      </header>

      {error && <div className="mb-5 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">{error}</div>}
      {loading && <ProfileSettingsSkeleton />}

      {!loading && profile && (
        <div className="space-y-5">
          <form className="rounded-xl border bg-card p-5" onSubmit={saveUsername}>
            <div>
              <h2 className="font-medium">Username</h2>
              <p className="mt-1 text-sm text-muted-foreground">This is how you appear across Iris.</p>
            </div>
            <div className="mt-4 flex max-w-lg items-center gap-2">
              <span className="text-muted-foreground">@</span>
              <input
                className="h-9 min-w-0 flex-1 rounded-md border bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-ring/20"
                aria-label="Username"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                autoComplete="username"
              />
              <Button
                uiVariant="solid"
                type="submit"
                disabled={busy || !username.trim() || username.trim() === profile.username}
              >
                Save
              </Button>
            </div>
          </form>

          <section className="rounded-xl border bg-card p-5">
            <div>
              <h2 className="font-medium">Personal websites</h2>
            </div>
            <form className="mt-4 flex max-w-lg items-center gap-2" onSubmit={addWebsite}>
              <Globe2 className="size-4 shrink-0 text-muted-foreground" />
              <input
                className="h-9 min-w-0 flex-1 rounded-md border bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-ring/20"
                aria-label="Personal website URL"
                value={websiteUrl}
                onChange={(event) => setWebsiteUrl(event.target.value)}
                placeholder="https://yoursite.com"
                inputMode="url"
              />
              <Button uiVariant="outline" type="submit" disabled={busy || !websiteUrl.trim()}>
                Add
              </Button>
            </form>
            {profile.websites.length > 0 && (
              <div className="mt-5 divide-y rounded-lg border">
                {profile.websites.map((website) => (
                  <div className="flex items-center justify-between gap-3 px-4 py-3" key={website.id}>
                    <a className="flex min-w-0 items-center gap-2 text-sm hover:text-primary" href={website.url} target="_blank" rel="noreferrer">
                      <span className="truncate font-medium">{website.canonical_domain}</span>
                      <ArrowUpRight size={14} />
                    </a>
                    <Button uiVariant="ghost" disabled={busy} onClick={() => removeWebsite(website.id)}>
                      Remove
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      )}
      <ToastRegion notice={notice} onDismiss={() => setNotice(null)} />
    </section>
  );
}

function ProfileSettingsSkeleton() {
  return (
    <div className="space-y-5" aria-label="Loading profile">
      {[0, 1].map((item) => (
        <div className="grid gap-3 rounded-xl border bg-card p-5" key={item}>
          <span className="h-5 w-32 animate-pulse rounded bg-muted" />
          <span className="h-9 w-full animate-pulse rounded bg-muted" />
        </div>
      ))}
    </div>
  );
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : 'Something went wrong';
}
