import { FormEvent, ReactNode, useEffect, useRef, useState } from 'react';
import { ArrowUpRight, Bell, BookOpen, UserPlus, Users } from 'lucide-react';
import {
  acceptFriendRequest,
  disconnectFriend,
  findUsers,
  getFriendRequests,
  getFriends,
  getFriendsFeed,
  getUserProfile,
  removeFriendRequest,
  sendFriendRequest,
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

const emptyRequests: FriendRequests = { incoming: [], outgoing: [] };

export function PeopleView() {
  const [feed, setFeed] = useState<FriendFeedItem[]>([]);
  const [friends, setFriends] = useState<Friendship[]>([]);
  const [requests, setRequests] = useState<FriendRequests>(emptyRequests);
  const [selectedProfile, setSelectedProfile] = useState<UserProfile | null>(null);
  const [peopleQuery, setPeopleQuery] = useState('');
  const [peopleResults, setPeopleResults] = useState<Person[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const networkRef = useRef<HTMLElement | null>(null);
  const didLoadPeopleRef = useRef(false);

  useEffect(() => {
    if (didLoadPeopleRef.current) return;
    didLoadPeopleRef.current = true;
    refresh();
  }, []);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const [feedPage, friendRows, requestRows] = await Promise.all([
        getFriendsFeed(),
        getFriends(),
        getFriendRequests(),
      ]);
      setFeed(feedPage.items);
      setFriends(friendRows);
      setRequests(requestRows);
      setSelectedProfile((current) => (
        current && friendRows.some((friendship) => friendship.person.username === current.username)
          ? current
          : null
      ));
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

  return (
    <section className="people-view">
      <header className="people-header">
        <div>
          <h1>People</h1>
          <p>Your private network and its reading activity.</p>
        </div>
      </header>

      {error && <StateMessage tone="error">{error}</StateMessage>}

      <div className="people-layout">
        <main className="people-feed-panel">
          <div className="people-section-heading">
            <div>
              <span>Feed</span>
              <h2>Reading activity</h2>
            </div>
          </div>
          {loading && <PeopleSkeleton />}
          {!loading && (
            <div className="people-feed">
              {feed.length === 0 && (
                <div className="people-feed-empty">
                  <BookOpen size={18} />
                  <strong>No reading activity yet</strong>
                  <p>Pages your friends save or finish will appear here.</p>
                  <Button
                    uiVariant="outline"
                    onClick={() => networkRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })}
                  >
                    Find people
                  </Button>
                </div>
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
                      <strong>@{item.person.username}</strong>{' '}
                      {item.status === 'read' ? 'read' : 'saved'}
                    </span>
                    <strong>{item.document.title || item.document.url}</strong>
                    <small>{item.document.source_domain} · {formatDate(item.activity_at)}</small>
                  </span>
                </button>
              ))}
            </div>
          )}
        </main>

        <aside className="people-network-panel" ref={networkRef}>
          <div className="people-network-heading">
            <div>
              <Users size={15} />
              <h2>Your network</h2>
            </div>
            {!loading && <span>{friends.length}</span>}
          </div>
          {loading ? (
            <NetworkSkeleton />
          ) : (
            <>
            <CorpusSearchForm
              className="people-search"
              value={peopleQuery}
              onChange={setPeopleQuery}
              onSubmit={searchPeople}
              placeholder="Search usernames"
              disabled={busy || !peopleQuery.trim()}
            />
              {peopleResults.length > 0 && (
                <div className="people-network-section">
                  <h3>People</h3>
                  <div className="people-list">
                    {peopleResults.map((person) => (
                      <div className="people-row" key={person.user_id}>
                        <span className="people-avatar">{initials(person)}</span>
                        <span>
                          <strong>@{person.username}</strong>
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
                </div>
              )}

              {requests.incoming.length > 0 && (
                <RequestList
                  title="Requests"
                  icon={<Bell size={13} />}
                  rows={requests.incoming}
                  busy={busy}
                  primaryLabel="Accept"
                  onPrimary={(id) => runAction(() => acceptFriendRequest(id))}
                  secondaryLabel="Decline"
                  onSecondary={(id) => runAction(() => removeFriendRequest(id))}
                />
              )}
              {requests.outgoing.length > 0 && (
                <RequestList
                  title="Sent"
                  rows={requests.outgoing}
                  busy={busy}
                  secondaryLabel="Cancel"
                  onSecondary={(id) => runAction(() => removeFriendRequest(id))}
                />
              )}

              <section className="people-network-section">
                <h3>Friends</h3>
                {friends.length === 0 && <div className="people-section-empty">No connections yet.</div>}
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
                          <strong>@{friendship.person.username}</strong>
                        </span>
                      </button>
                      <Button
                        uiVariant="ghost"
                        disabled={busy}
                        onClick={() => runAction(() => disconnectFriend(friendship.id))}
                      >
                        Remove
                      </Button>
                    </div>
                  ))}
                </div>
                {selectedProfile && <ProfileSummary profile={selectedProfile} />}
              </section>
            </>
          )}
        </aside>
      </div>
    </section>
  );
}

function RequestList({
  title,
  icon,
  rows,
  busy,
  primaryLabel,
  secondaryLabel,
  onPrimary,
  onSecondary,
}: {
  title: string;
  icon?: ReactNode;
  rows: Friendship[];
  busy: boolean;
  primaryLabel?: string;
  secondaryLabel: string;
  onPrimary?: (id: number) => void;
  onSecondary: (id: number) => void;
}) {
  return (
    <section className="people-network-section">
      <h3>{icon}{title}<span>{rows.length}</span></h3>
      <div className="people-list">
        {rows.map((friendship) => (
          <div className="people-row" key={friendship.id}>
            <span className="people-avatar">{initials(friendship.person)}</span>
            <span>
              <strong>@{friendship.person.username}</strong>
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
      <h3>@{profile.username}</h3>
      {profile.bio && <p>{profile.bio}</p>}
      {profile.websites.map((website) => (
        <a key={website.id} href={website.url} target="_blank" rel="noreferrer">
          {website.label || website.canonical_domain} <ArrowUpRight size={13} />
        </a>
      ))}
    </div>
  );
}

function initials(person: Person | UserProfile) {
  return person.username
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

function PeopleSkeleton() {
  return (
    <div className="people-loading" aria-label="Loading people">
      {[0, 1, 2].map((item) => (
        <div className="people-loading-row" key={item}>
          <span />
          <span className="skeleton-line" />
        </div>
      ))}
    </div>
  );
}

function NetworkSkeleton() {
  return (
    <div className="people-network-skeleton skeleton-stack" aria-label="Loading network">
      <span className="skeleton-line" />
      <span className="skeleton-line" />
      <span className="skeleton-line" />
    </div>
  );
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : 'Something went wrong';
}
