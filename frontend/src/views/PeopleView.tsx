import { FormEvent, useEffect, useState } from 'react';
import { ArrowUpRight, Globe2, UserPlus } from 'lucide-react';
import {
  acceptFriendRequest,
  attachProfileWebsite,
  deleteProfileWebsite,
  disconnectFriend,
  findUsers,
  getFriendRequests,
  getFriends,
  getFriendsFeed,
  getMyProfile,
  getUserProfile,
  removeFriendRequest,
  sendFriendRequest,
  updateMyProfile,
} from '../api';
import { documentPath, navigateTo } from '../app/navigation';
import { CorpusSearchForm } from '../CorpusSearchForm';
import { Button, StateMessage } from '../components/ui';
import type {
  FriendFeedItem,
  FriendRequests,
  Friendship,
  Person,
  UserProfile,
} from '../types';

type PeopleTab = 'feed' | 'friends' | 'requests' | 'profile';

const emptyRequests: FriendRequests = { incoming: [], outgoing: [] };

export function PeopleView() {
  const [tab, setTab] = useState<PeopleTab>('feed');
  const [feed, setFeed] = useState<FriendFeedItem[]>([]);
  const [friends, setFriends] = useState<Friendship[]>([]);
  const [requests, setRequests] = useState<FriendRequests>(emptyRequests);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [selectedProfile, setSelectedProfile] = useState<UserProfile | null>(null);
  const [peopleQuery, setPeopleQuery] = useState('');
  const [peopleResults, setPeopleResults] = useState<Person[]>([]);
  const [profileForm, setProfileForm] = useState({ username: '', displayName: '', bio: '' });
  const [websiteForm, setWebsiteForm] = useState({ url: '', label: '' });
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    refresh();
  }, []);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const [feedPage, friendRows, requestRows, ownProfile] = await Promise.all([
        getFriendsFeed(),
        getFriends(),
        getFriendRequests(),
        getMyProfile(),
      ]);
      setFeed(feedPage.items);
      setFriends(friendRows);
      setRequests(requestRows);
      setProfile(ownProfile);
      setProfileForm({
        username: ownProfile.username,
        displayName: ownProfile.display_name ?? '',
        bio: ownProfile.bio ?? '',
      });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  async function searchPeople(event: FormEvent) {
    event.preventDefault();
    if (!peopleQuery.trim()) return;
    setBusy(true);
    setError(null);
    try {
      setPeopleResults(await findUsers(peopleQuery));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function runAction(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      await refresh();
      if (peopleQuery.trim()) setPeopleResults(await findUsers(peopleQuery));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function openFriendProfile(friendship: Friendship) {
    setBusy(true);
    setError(null);
    try {
      setSelectedProfile(await getUserProfile(friendship.person.username));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function saveProfile(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const updated = await updateMyProfile({
        username: profileForm.username,
        display_name: profileForm.displayName,
        bio: profileForm.bio,
      });
      setProfile(updated);
      setProfileForm({
        username: updated.username,
        displayName: updated.display_name ?? '',
        bio: updated.bio ?? '',
      });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function addWebsite(event: FormEvent) {
    event.preventDefault();
    if (!websiteForm.url.trim()) return;
    await runAction(async () => {
      await attachProfileWebsite({
        url: websiteForm.url,
        label: websiteForm.label || null,
      });
      setWebsiteForm({ url: '', label: '' });
    });
  }

  return (
    <section className="people-view">
      <header className="people-header">
        <div>
          <h1>People</h1>
          <p>Private profiles, friends, and what your friends are reading.</p>
        </div>
        <div className="people-tabs" role="tablist" aria-label="People sections">
          {(['feed', 'friends', 'requests', 'profile'] as PeopleTab[]).map((item) => (
            <button
              key={item}
              type="button"
              role="tab"
              aria-selected={tab === item}
              className={tab === item ? 'people-tab people-tab-active' : 'people-tab'}
              onClick={() => setTab(item)}
            >
              {item === 'requests' && requests.incoming.length > 0
                ? `Requests ${requests.incoming.length}`
                : capitalize(item)}
            </button>
          ))}
        </div>
      </header>

      {error && <StateMessage tone="error">{error}</StateMessage>}
      {loading && <StateMessage>Loading people…</StateMessage>}

      {!loading && tab === 'feed' && (
        <div className="people-feed">
          {feed.length === 0 && (
            <StateMessage>Your friends' saved and read pages will appear here.</StateMessage>
          )}
          {feed.map((item) => (
            <button
              key={`${item.person.user_id}-${item.document.uuid}-${item.activity_at}`}
              type="button"
              className="people-feed-row"
              onClick={() => navigateTo(documentPath(item.document.uuid))}
            >
              <span className="people-avatar">{initials(item.person)}</span>
              <span className="people-feed-copy">
                <span>
                  <strong>{personName(item.person)}</strong>{' '}
                  {item.status === 'read' ? 'read' : 'saved'}
                </span>
                <strong>{item.document.title || item.document.url}</strong>
                <small>{item.document.source_domain} · {formatDate(item.activity_at)}</small>
              </span>
            </button>
          ))}
        </div>
      )}

      {!loading && tab === 'friends' && (
        <div className="people-grid">
          <section className="people-panel">
            <h2>Find people</h2>
            <CorpusSearchForm
              className="people-search"
              value={peopleQuery}
              onChange={setPeopleQuery}
              onSubmit={searchPeople}
              placeholder="Search by name or username"
              disabled={busy || !peopleQuery.trim()}
            />
            <div className="people-list">
              {peopleResults.map((person) => (
                <div className="people-row" key={person.user_id}>
                  <span className="people-avatar">{initials(person)}</span>
                  <span>
                    <strong>{personName(person)}</strong>
                    <small>@{person.username}</small>
                  </span>
                  {person.relationship === 'none' && (
                    <Button
                      uiVariant="outline"
                      disabled={busy}
                      onClick={() => runAction(() => sendFriendRequest(person.user_id))}
                    >
                      <UserPlus size={14} /> Add
                    </Button>
                  )}
                  {person.relationship !== 'none' && (
                    <small className="people-relationship">{relationshipLabel(person.relationship)}</small>
                  )}
                </div>
              ))}
            </div>
          </section>

          <section className="people-panel">
            <h2>Friends</h2>
            {friends.length === 0 && <StateMessage>No connected friends yet.</StateMessage>}
            <div className="people-list">
              {friends.map((friendship) => (
                <div className="people-row" key={friendship.id}>
                  <button
                    type="button"
                    className="people-row-profile"
                    onClick={() => openFriendProfile(friendship)}
                  >
                    <span className="people-avatar">{initials(friendship.person)}</span>
                    <span>
                      <strong>{personName(friendship.person)}</strong>
                      <small>@{friendship.person.username}</small>
                    </span>
                  </button>
                  <Button
                    uiVariant="ghost"
                    disabled={busy}
                    onClick={() => runAction(() => disconnectFriend(friendship.id))}
                  >
                    Disconnect
                  </Button>
                </div>
              ))}
            </div>
            {selectedProfile && <ProfileSummary profile={selectedProfile} />}
          </section>
        </div>
      )}

      {!loading && tab === 'requests' && (
        <div className="people-grid">
          <RequestList
            title="Incoming"
            rows={requests.incoming}
            empty="No incoming requests."
            busy={busy}
            primaryLabel="Accept"
            onPrimary={(id) => runAction(() => acceptFriendRequest(id))}
            secondaryLabel="Decline"
            onSecondary={(id) => runAction(() => removeFriendRequest(id))}
          />
          <RequestList
            title="Sent"
            rows={requests.outgoing}
            empty="No sent requests."
            busy={busy}
            secondaryLabel="Cancel"
            onSecondary={(id) => runAction(() => removeFriendRequest(id))}
          />
        </div>
      )}

      {!loading && tab === 'profile' && profile && (
        <div className="people-grid">
          <form className="people-panel people-form" onSubmit={saveProfile}>
            <h2>Your profile</h2>
            <label>
              Display name
              <input
                value={profileForm.displayName}
                onChange={(event) => setProfileForm((value) => ({ ...value, displayName: event.target.value }))}
              />
            </label>
            <label>
              Username
              <input
                value={profileForm.username}
                onChange={(event) => setProfileForm((value) => ({ ...value, username: event.target.value }))}
              />
            </label>
            <label>
              Bio
              <textarea
                value={profileForm.bio}
                onChange={(event) => setProfileForm((value) => ({ ...value, bio: event.target.value }))}
                rows={5}
              />
            </label>
            <Button uiVariant="solid" type="submit" disabled={busy}>Save profile</Button>
            <small>Only connected friends can open this profile.</small>
          </form>

          <section className="people-panel people-form">
            <h2>Personal websites</h2>
            <form className="people-website-form" onSubmit={addWebsite}>
              <label>
                Website URL
                <input
                  value={websiteForm.url}
                  onChange={(event) => setWebsiteForm((value) => ({ ...value, url: event.target.value }))}
                  placeholder="https://example.com"
                />
              </label>
              <label>
                Label
                <input
                  value={websiteForm.label}
                  onChange={(event) => setWebsiteForm((value) => ({ ...value, label: event.target.value }))}
                  placeholder="Writing"
                />
              </label>
              <Button uiVariant="outline" type="submit" disabled={busy || !websiteForm.url.trim()}>
                <Globe2 size={14} /> Attach website
              </Button>
            </form>
            <div className="people-websites">
              {profile.websites.map((website) => (
                <div className="people-website-row" key={website.id}>
                  <a href={website.url} target="_blank" rel="noreferrer">
                    <strong>{website.label || website.canonical_domain}</strong>
                    <small>{website.canonical_domain} · {website.source_status}</small>
                    <ArrowUpRight size={14} />
                  </a>
                  <Button
                    uiVariant="ghost"
                    disabled={busy}
                    onClick={() => runAction(() => deleteProfileWebsite(website.id))}
                  >
                    Remove
                  </Button>
                </div>
              ))}
            </div>
            <small>Website ownership is not verified yet.</small>
          </section>
        </div>
      )}
    </section>
  );
}

function RequestList({
  title,
  rows,
  empty,
  busy,
  primaryLabel,
  secondaryLabel,
  onPrimary,
  onSecondary,
}: {
  title: string;
  rows: Friendship[];
  empty: string;
  busy: boolean;
  primaryLabel?: string;
  secondaryLabel: string;
  onPrimary?: (id: number) => void;
  onSecondary: (id: number) => void;
}) {
  return (
    <section className="people-panel">
      <h2>{title}</h2>
      {rows.length === 0 && <StateMessage>{empty}</StateMessage>}
      <div className="people-list">
        {rows.map((friendship) => (
          <div className="people-row" key={friendship.id}>
            <span className="people-avatar">{initials(friendship.person)}</span>
            <span>
              <strong>{personName(friendship.person)}</strong>
              <small>@{friendship.person.username}</small>
            </span>
            <span className="people-actions">
              {primaryLabel && onPrimary && (
                <Button uiVariant="solid" disabled={busy} onClick={() => onPrimary(friendship.id)}>
                  {primaryLabel}
                </Button>
              )}
              <Button uiVariant="ghost" disabled={busy} onClick={() => onSecondary(friendship.id)}>
                {secondaryLabel}
              </Button>
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}

function ProfileSummary({ profile }: { profile: UserProfile }) {
  return (
    <div className="people-profile-summary">
      <h3>{personName(profile)}</h3>
      <small>@{profile.username}</small>
      {profile.bio && <p>{profile.bio}</p>}
      {profile.websites.map((website) => (
        <a key={website.id} href={website.url} target="_blank" rel="noreferrer">
          {website.label || website.canonical_domain} <ArrowUpRight size={13} />
        </a>
      ))}
    </div>
  );
}

function personName(person: Person | UserProfile) {
  return person.display_name || person.username;
}

function initials(person: Person | UserProfile) {
  return personName(person)
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join('');
}

function relationshipLabel(value: Person['relationship']) {
  if (value === 'connected') return 'Friend';
  if (value === 'requested_outgoing') return 'Requested';
  if (value === 'requested_incoming') return 'Request received';
  return value;
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    year: new Date(value).getFullYear() === new Date().getFullYear() ? undefined : 'numeric',
  }).format(new Date(value));
}

function capitalize(value: string) {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : 'Something went wrong';
}
