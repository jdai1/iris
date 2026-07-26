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
    <section className="mx-auto min-h-svh w-full max-w-6xl p-5 sm:p-8">
      <header className="mb-8">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">People</h1>
          <p className="mt-1 text-sm text-muted-foreground">Your private network and its reading activity.</p>
        </div>
      </header>

      {error && <StateMessage tone="error">{error}</StateMessage>}

      <div className="mt-5 grid gap-8 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <main className="min-w-0">
          <div className="border-b pb-3">
            <div>
              <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Feed</span>
              <h2 className="text-base font-medium">Reading activity</h2>
            </div>
          </div>
          {loading && <PeopleSkeleton />}
          {!loading && (
            <div className="divide-y">
              {feed.length === 0 && (
                <div className="grid min-h-[26rem] place-items-center content-center gap-3 px-6 py-16 text-center">
                  <span className="grid size-10 place-items-center rounded-full bg-muted text-muted-foreground"><BookOpen size={18} /></span>
                  <strong className="font-medium">No reading activity yet</strong>
                  <p className="max-w-xs text-sm text-muted-foreground">Pages your friends save or finish will appear here.</p>
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
                  className="grid w-full grid-cols-[2.25rem_minmax(0,1fr)] gap-3 px-2 py-4 text-left hover:bg-muted/50"
                  onClick={() => navigateTo(documentPath(item.document.uuid))}
                >
                  <span className="grid size-9 place-items-center rounded-full bg-primary/10 text-xs font-semibold text-primary">{initials(item.person)}</span>
                  <span className="min-w-0 text-sm">
                    <span className="block text-muted-foreground">
                      <strong>@{item.person.username}</strong>{' '}
                      {item.status === 'read' ? 'read' : 'saved'}
                    </span>
                    <strong className="mt-1 block truncate font-medium text-foreground">{item.document.title || item.document.url}</strong>
                    <small className="mt-0.5 block text-muted-foreground">{item.document.source_domain} · {formatDate(item.activity_at)}</small>
                  </span>
                </button>
              ))}
            </div>
          )}
        </main>

        <aside className="self-start lg:border-l lg:pl-6" ref={networkRef}>
          <div className="flex items-center justify-between border-b pb-3">
            <div className="flex items-center gap-2">
              <Users size={15} />
              <h2 className="text-sm font-medium">Your network</h2>
            </div>
            {!loading && <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">{friends.length}</span>}
          </div>
          {loading ? (
            <NetworkSkeleton />
          ) : (
            <>
            <CorpusSearchForm
              className="my-4 min-h-10"
              value={peopleQuery}
              onChange={setPeopleQuery}
              onSubmit={searchPeople}
              placeholder="Search usernames"
              disabled={busy || !peopleQuery.trim()}
            />
              {peopleResults.length > 0 && (
                <div className="border-t py-4">
                  <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">People</h3>
                  <div className="space-y-1">
                    {peopleResults.map((person) => (
                      <div className="grid grid-cols-[2rem_minmax(0,1fr)_auto] items-center gap-2 rounded-md px-2 py-2 hover:bg-muted/50" key={person.user_id}>
                        <span className="grid size-8 place-items-center rounded-full bg-primary/10 text-xs font-semibold text-primary">{initials(person)}</span>
                        <span className="min-w-0 truncate text-sm">
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
                          <small className="text-xs text-muted-foreground">{relationshipLabel(person.relationship)}</small>
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

              <section className="border-t py-4">
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Friends</h3>
                {friends.length === 0 && <div className="py-4 text-center text-sm text-muted-foreground">No connections yet.</div>}
                <div className="space-y-1">
                  {friends.map((friendship) => (
                    <div className="flex items-center justify-between gap-2 rounded-md px-2 py-2 hover:bg-muted/50" key={friendship.id}>
                      <button
                        type="button"
                        className="flex min-w-0 flex-1 items-center gap-2 text-left"
                        onClick={() => openFriendProfile(friendship)}
                      >
                        <span className="grid size-8 shrink-0 place-items-center rounded-full bg-primary/10 text-xs font-semibold text-primary">{initials(friendship.person)}</span>
                        <span className="min-w-0 truncate text-sm">
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
    <section className="border-t py-4">
      <h3 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{icon}{title}<span className="ml-auto rounded-full bg-muted px-2 py-0.5">{rows.length}</span></h3>
      <div className="space-y-1">
        {rows.map((friendship) => (
          <div className="grid grid-cols-[2rem_minmax(0,1fr)_auto] items-center gap-2 rounded-md px-2 py-2 hover:bg-muted/50" key={friendship.id}>
            <span className="grid size-8 place-items-center rounded-full bg-primary/10 text-xs font-semibold text-primary">{initials(friendship.person)}</span>
            <span className="min-w-0 truncate text-sm">
              <strong>@{friendship.person.username}</strong>
            </span>
            <span className="flex items-center gap-1">
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
    <div className="mt-4 border-t pt-4">
      <h3 className="text-sm font-medium">@{profile.username}</h3>
      {profile.bio && <p className="mt-1 text-xs text-muted-foreground">{profile.bio}</p>}
      {profile.websites.map((website) => (
        <a className="mt-2 flex items-center gap-1 text-xs text-primary hover:underline" key={website.id} href={website.url} target="_blank" rel="noreferrer">
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
    <div className="divide-y" aria-label="Loading people">
      {[0, 1, 2].map((item) => (
        <div className="grid grid-cols-[2.25rem_minmax(0,1fr)] gap-3 px-5 py-4" key={item}>
          <span className="size-9 animate-pulse rounded-full bg-muted" />
          <span className="h-10 animate-pulse rounded bg-muted" />
        </div>
      ))}
    </div>
  );
}

function NetworkSkeleton() {
  return (
    <div className="grid gap-2 p-4" aria-label="Loading network">
      <span className="h-9 animate-pulse rounded bg-muted" />
      <span className="h-9 animate-pulse rounded bg-muted" />
      <span className="h-9 animate-pulse rounded bg-muted" />
    </div>
  );
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : 'Something went wrong';
}
