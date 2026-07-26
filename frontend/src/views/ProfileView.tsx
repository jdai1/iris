import { FormEvent, useEffect, useState } from 'react';
import { ArrowUpRight, Globe2 } from 'lucide-react';
import {
  attachProfileWebsite,
  deleteProfileWebsite,
  getMyProfile,
  updateMyProfile,
} from '../api';
import { Button } from '../components/ui';
import type { UserProfile } from '../types';

export function ProfileView({ onUsernameChange }: { onUsernameChange?: (username: string) => void }) {
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [username, setUsername] = useState('');
  const [websiteUrl, setWebsiteUrl] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
    } catch (err) {
      setError(errorMessage(err));
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
    <section className="profile-settings-view">
      <header className="profile-settings-header">
        <span>Settings</span>
        <h1>My profile</h1>
        <p>Only connected friends can open your profile.</p>
      </header>

      {error && <div className="profile-settings-error">{error}</div>}
      {loading && <ProfileSettingsSkeleton />}

      {!loading && profile && (
        <div className="profile-settings-sections">
          <form className="profile-settings-section" onSubmit={saveUsername}>
            <div>
              <h2>Username</h2>
              <p>This is how you appear across Iris.</p>
            </div>
            <div className="profile-settings-inline">
              <span>@</span>
              <input
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

          <section className="profile-settings-section">
            <div>
              <h2>Personal websites</h2>
              <p>Attached sites are added to the Iris indexing queue.</p>
            </div>
            <form className="profile-settings-inline profile-settings-website-form" onSubmit={addWebsite}>
              <Globe2 size={15} />
              <input
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
            <div className="profile-settings-websites">
              {profile.websites.length === 0 && (
                <p className="profile-settings-empty">No personal website attached.</p>
              )}
              {profile.websites.map((website) => (
                <div className="profile-settings-website" key={website.id}>
                  <a href={website.url} target="_blank" rel="noreferrer">
                    <span>{website.canonical_domain}</span>
                    <small>{website.source_status}</small>
                    <ArrowUpRight size={14} />
                  </a>
                  <Button uiVariant="ghost" disabled={busy} onClick={() => removeWebsite(website.id)}>
                    Remove
                  </Button>
                </div>
              ))}
            </div>
          </section>
        </div>
      )}
    </section>
  );
}

function ProfileSettingsSkeleton() {
  return (
    <div className="profile-settings-sections" aria-label="Loading profile">
      {[0, 1].map((item) => (
        <div className="profile-settings-section profile-settings-skeleton" key={item}>
          <span className="skeleton-line" />
          <span className="skeleton-line" />
        </div>
      ))}
    </div>
  );
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : 'Something went wrong';
}
