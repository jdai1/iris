import { FormEvent, ReactNode, useCallback, useEffect, useRef, useState } from 'react';
import { ArrowLeft, ArrowUpRight, Bell, BookOpen, Check, Clock3, Heart, Highlighter, Loader2, Minus, Pencil, UserPlus, Users, X } from 'lucide-react';
import {
  acceptFriendRequest,
  disconnectFriend,
  findUsers,
  getFriendRequests,
  getFriends,
  getFriendsFeed,
  getUserFriends,
  getUserProfile,
  removeFriendRequest,
  sendFriendRequest,
} from '../api';
import { documentPath, navigateTo, peopleProfilePath, peopleUsernameFromPath } from '../app/navigation';
import { CorpusSearchForm } from '../CorpusSearchForm';
import { DocumentActionsMenu } from '../components/DocumentActionsMenu';
import { Button, StateMessage } from '../components/ui';
import type { BookshelfEntry, BookshelfStatus, FriendFeedItem, FriendRequests, Friendship, Person, UserProfile } from '../types';

const FEED_PAGE_SIZE = 25;
const NETWORK_SEEN_STORAGE_KEY = 'iris.people.networkSeenAt';
const emptyRequests: FriendRequests = { incoming: [], outgoing: [] };

export function PeopleView() {
  const [routeUsername, setRouteUsername] = useState(() => peopleUsernameFromPath(window.location.pathname));
  const [friends, setFriends] = useState<Friendship[]>([]);
  const [requests, setRequests] = useState<FriendRequests>(emptyRequests);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [profileFriends, setProfileFriends] = useState<Person[]>([]);
  const [peopleQuery, setPeopleQuery] = useState('');
  const [peopleResults, setPeopleResults] = useState<Person[]>([]);
  const [networkOpen, setNetworkOpen] = useState(false);
  const [networkSeenAt, setNetworkSeenAt] = useState(() => window.localStorage.getItem(NETWORK_SEEN_STORAGE_KEY));
  const [acceptedNotifications, setAcceptedNotifications] = useState<Friendship[]>([]);
  const [networkLoading, setNetworkLoading] = useState(true);
  const [profileLoading, setProfileLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const canViewProfileDetails = !routeUsername || (
    profile?.username === routeUsername
    && (profile.relationship === 'connected' || profile.relationship === 'self')
  );
  const activity = useFriendActivity(routeUsername, canViewProfileDetails);

  useEffect(() => {
    const syncRoute = () => setRouteUsername(peopleUsernameFromPath(window.location.pathname));
    window.addEventListener('popstate', syncRoute);
    return () => window.removeEventListener('popstate', syncRoute);
  }, []);

  useEffect(() => {
    setNetworkOpen(false);
  }, [routeUsername]);

  useEffect(() => {
    refreshNetwork();
  }, []);

  useEffect(() => {
    if (!networkOpen) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setNetworkOpen(false);
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [networkOpen]);

  useEffect(() => {
    if (!routeUsername) {
      setProfile(null);
      setProfileFriends([]);
      setProfileLoading(false);
      return;
    }
    let cancelled = false;
    setProfile(null);
    setProfileFriends([]);
    setProfileLoading(true);
    setError(null);
    getUserProfile(routeUsername)
      .then(async (nextProfile) => {
        const canViewPrivate = nextProfile.relationship === 'connected' || nextProfile.relationship === 'self';
        const nextFriends = canViewPrivate ? await getUserFriends(routeUsername) : [];
        if (!cancelled) {
          setProfile(nextProfile);
          setProfileFriends(nextFriends);
        }
      })
      .catch((err) => {
        if (!cancelled) setError(errorMessage(err));
      })
      .finally(() => {
        if (!cancelled) setProfileLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [routeUsername]);

  async function refreshNetwork(showLoading = true) {
    if (showLoading) setNetworkLoading(true);
    setError(null);
    try {
      const [friendRows, requestRows] = await Promise.all([getFriends(), getFriendRequests()]);
      setFriends(friendRows);
      setRequests(requestRows);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      if (showLoading) setNetworkLoading(false);
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
      await Promise.all([refreshNetwork(false), activity.reload()]);
      if (peopleQuery.trim()) setPeopleResults(await findUsers(peopleQuery));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function runProfileAction(action: () => Promise<unknown>) {
    if (!routeUsername) return;
    setBusy(true);
    setError(null);
    try {
      await action();
      await refreshNetwork(false);
      setProfile(await getUserProfile(routeUsername));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const newlyAccepted = friends.filter((friendship) => (
    friendship.requested_by_me
    && (!networkSeenAt || new Date(friendship.updated_at).getTime() > new Date(networkSeenAt).getTime())
  ));
  const notificationCount = requests.incoming.length + newlyAccepted.length;
  const profileIncomingRequest = requests.incoming.find((request) => request.person.user_id === profile?.user_id);

  function openNetwork() {
    setAcceptedNotifications(newlyAccepted);
    setNetworkOpen(true);
    const now = new Date().toISOString();
    window.localStorage.setItem(NETWORK_SEEN_STORAGE_KEY, now);
    setNetworkSeenAt(now);
  }

  const visibleError = error || activity.error;

  if (routeUsername) {
    return (
      <PeopleProfilePage
        username={routeUsername}
        profile={profile}
        friends={profileFriends}
        loading={profileLoading}
        error={visibleError}
        activity={activity}
        busy={busy}
        onConnect={() => runProfileAction(() => sendFriendRequest(profile!.user_id))}
        onAcceptRequest={profileIncomingRequest
          ? () => runProfileAction(() => acceptFriendRequest(profileIncomingRequest.id))
          : undefined}
      />
    );
  }

  return (
    <section className="mx-auto min-h-svh w-full max-w-6xl p-5 sm:p-8">
      {visibleError && <StateMessage tone="error">{visibleError}</StateMessage>}

      <div>
        <main className="min-w-0">
          <div className="border-b pb-3">
            <div className="flex h-8 items-center justify-between gap-4">
              <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">From your circle</span>
              <Button
                className="relative -mr-2 size-8 text-muted-foreground hover:text-foreground"
                uiVariant="ghost"
                size="icon"
                type="button"
                onClick={openNetwork}
                aria-label={notificationCount ? `Open network, ${notificationCount} notifications` : 'Open network'}
                title="Network"
              >
                <Users size={18} />
                {notificationCount > 0 && (
                  <span className="absolute -right-1 -top-1 grid min-w-5 place-items-center rounded-full bg-primary px-1 text-[10px] font-semibold leading-5 text-primary-foreground">
                    {notificationCount > 99 ? '99+' : notificationCount}
                  </span>
                )}
              </Button>
            </div>
          </div>
          <ActivityFeed
            activity={activity}
            emptyAction={openNetwork}
            emptyActionLabel="Find people"
          />
        </main>

      </div>
      {networkOpen && (
        <>
          <button className="fixed inset-0 z-40 bg-black/20 animate-in fade-in-0" type="button" aria-label="Close network" onClick={() => setNetworkOpen(false)} />
          <NetworkPanel
            loading={networkLoading}
            busy={busy}
            friends={friends}
            requests={requests}
            acceptedNotifications={acceptedNotifications}
            peopleQuery={peopleQuery}
            peopleResults={peopleResults}
            onClose={() => setNetworkOpen(false)}
            onPeopleQueryChange={setPeopleQuery}
            onSearchPeople={searchPeople}
            onAction={runAction}
          />
        </>
      )}
    </section>
  );
}

function NetworkPanel({
  loading,
  busy,
  friends,
  requests,
  acceptedNotifications,
  peopleQuery,
  peopleResults,
  onPeopleQueryChange,
  onSearchPeople,
  onAction,
  onClose,
}: {
  loading: boolean;
  busy: boolean;
  friends: Friendship[];
  requests: FriendRequests;
  acceptedNotifications: Friendship[];
  peopleQuery: string;
  peopleResults: Person[];
  onPeopleQueryChange: (value: string) => void;
  onSearchPeople: (event: FormEvent) => void;
  onAction: (action: () => Promise<unknown>) => void;
  onClose: () => void;
}) {
  const discoverablePeople = peopleResults.filter((person) => person.relationship === 'none');
  return (
    <aside className="fixed inset-y-0 right-0 z-50 w-full max-w-sm overflow-y-auto border-l bg-background shadow-xl animate-in slide-in-from-right-full">
      <div className="sticky top-0 z-10 flex h-14 items-center justify-between border-b bg-background/95 px-4 backdrop-blur">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-medium">Network</h2>
          {!loading && <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">{friends.length}</span>}
        </div>
        <Button uiVariant="ghost" size="icon" type="button" onClick={onClose} aria-label="Close network">
          <X size={17} />
        </Button>
      </div>
      <div className="px-4">
      {loading ? (
        <NetworkSkeleton />
      ) : (
        <>
          <CorpusSearchForm
            className="my-4 min-h-10"
            value={peopleQuery}
            onChange={onPeopleQueryChange}
            onSubmit={onSearchPeople}
            placeholder="Search usernames"
            disabled={busy || !peopleQuery.trim()}
          />

          {discoverablePeople.length > 0 && (
            <section className="border-t py-4">
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">People</h3>
              <div className="space-y-1">
                {discoverablePeople.map((person) => (
                  <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-2 rounded-md px-2 py-2 hover:bg-muted/50" key={person.user_id}>
                    <button className="min-w-0 truncate text-left text-sm font-semibold hover:underline" type="button" onClick={() => openPeopleProfile(person.username)}>
                      @{person.username}
                    </button>
                    <Button uiVariant="outline" disabled={busy} onClick={() => onAction(() => sendFriendRequest(person.user_id))}>
                      <UserPlus size={14} /> Add
                    </Button>
                  </div>
                ))}
              </div>
            </section>
          )}

          {requests.incoming.length > 0 && (
            <RequestList
              title="Requests"
              icon={<Bell size={13} />}
              rows={requests.incoming}
              busy={busy}
              primaryLabel="Accept"
              onPrimary={(id) => onAction(() => acceptFriendRequest(id))}
              secondaryLabel="Decline"
              onSecondary={(id) => onAction(() => removeFriendRequest(id))}
            />
          )}
          {requests.outgoing.length > 0 && (
            <RequestList
              title="Sent"
              rows={requests.outgoing}
              busy={busy}
              secondaryLabel="Cancel"
              onSecondary={(id) => onAction(() => removeFriendRequest(id))}
            />
          )}

          {acceptedNotifications.length > 0 && (
            <section className="border-t py-4">
              <h3 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                <Check size={13} /> Accepted
                <span className="ml-auto rounded-full bg-muted px-2 py-0.5">{acceptedNotifications.length}</span>
              </h3>
              <div className="space-y-1">
                {acceptedNotifications.map((friendship) => (
                  <button className="flex w-full items-center gap-2 rounded-md px-2 py-2 text-left hover:bg-muted/50" key={friendship.id} type="button" onClick={() => openPeopleProfile(friendship.person.username)}>
                    <span className="min-w-0 text-sm"><strong className="block truncate">@{friendship.person.username}</strong><small className="text-muted-foreground">Accepted your request</small></span>
                  </button>
                ))}
              </div>
            </section>
          )}

          <section className="border-t py-4">
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Friends</h3>
            {friends.length === 0 && <div className="py-4 text-center text-sm text-muted-foreground">No connections yet.</div>}
            <div className="space-y-1">
              {friends.map((friendship) => (
                <div className="flex items-center justify-between gap-2 rounded-md px-2 py-2 hover:bg-muted/50" key={friendship.id}>
                  <button type="button" className="flex min-w-0 flex-1 items-center gap-2 text-left" onClick={() => openPeopleProfile(friendship.person.username)}>
                    <strong className="min-w-0 truncate text-sm">@{friendship.person.username}</strong>
                  </button>
                  <Button uiVariant="ghost" disabled={busy} onClick={() => onAction(() => disconnectFriend(friendship.id))}>
                    Remove
                  </Button>
                </div>
              ))}
            </div>
          </section>
        </>
      )}
      </div>
    </aside>
  );
}

function PeopleProfilePage({
  username,
  profile,
  friends,
  loading,
  error,
  activity,
  busy,
  onConnect,
  onAcceptRequest,
}: {
  username: string;
  profile: UserProfile | null;
  friends: Person[];
  loading: boolean;
  error: string | null;
  activity: FriendActivity;
  busy: boolean;
  onConnect: () => void;
  onAcceptRequest?: () => void;
}) {
  const canViewDetails = profile?.relationship === 'connected' || profile?.relationship === 'self';
  return (
    <section className="mx-auto min-h-svh w-full max-w-4xl p-5 sm:p-8">
      <Button className="mb-6 -ml-2" uiVariant="ghost" type="button" onClick={() => navigateTo('/people')}>
        <ArrowLeft size={15} /> Activity
      </Button>
      {error && <StateMessage tone="error">{error}</StateMessage>}
      {loading && <ProfileSkeleton />}
      {!loading && profile && (
        <>
          <header className="mb-8 border-b pb-6">
            <h1 className="truncate text-2xl font-semibold tracking-tight">@{profile.username}</h1>
            {profile.bio && <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">{profile.bio}</p>}
            {profile.websites.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-x-4 gap-y-2">
                {profile.websites.map((website) => (
                  <a className="inline-flex items-center gap-1 text-sm text-primary hover:underline" key={website.id} href={website.url} target="_blank" rel="noreferrer">
                    {website.label || website.canonical_domain} <ArrowUpRight size={13} />
                  </a>
                ))}
              </div>
            )}
          </header>
          {!canViewDetails ? (
            <div className="grid min-h-72 place-items-center content-center gap-3 text-center">
              <strong className="font-medium">Connect to see more</strong>
              <p className="max-w-sm text-sm text-muted-foreground">Friends and reading activity are only visible to connections.</p>
              {profile.relationship === 'none' && <Button uiVariant="solid" disabled={busy} onClick={onConnect}><UserPlus size={14} /> Connect</Button>}
              {profile.relationship === 'requested_outgoing' && <Button uiVariant="outline" disabled>Request sent</Button>}
              {profile.relationship === 'requested_incoming' && (
                <Button uiVariant="solid" disabled={busy || !onAcceptRequest} onClick={onAcceptRequest}>Accept request</Button>
              )}
            </div>
          ) : (
            <>
              <section className="mb-8 border-b pb-6">
                <div className="mb-3 flex items-center gap-2">
                  <h2 className="text-sm font-medium">Friends</h2>
                  <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">{friends.length}</span>
                </div>
                {friends.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No connections yet.</p>
                ) : (
                  <div className="flex flex-wrap gap-2">
                    {friends.map((friend) => {
                      const visibleProfile = friend.relationship === 'connected' || friend.relationship === 'self';
                      const content = <span className="max-w-44 truncate text-sm font-medium">@{friend.username}</span>;
                      return visibleProfile ? (
                        <button className="inline-flex items-center rounded-md px-2 py-1.5 hover:bg-muted" key={friend.user_id} type="button" onClick={() => openPeopleProfile(friend.username)}>
                          {content}
                        </button>
                      ) : (
                        <span className="inline-flex items-center rounded-md px-2 py-1.5 text-muted-foreground" key={friend.user_id}>{content}</span>
                      );
                    })}
                  </div>
                )}
              </section>
              <div className="border-b pb-3">
                <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Activity</span>
                <h2 className="text-base font-medium">Reading history</h2>
              </div>
              <ActivityFeed activity={activity} profileUsername={username} />
            </>
          )}
        </>
      )}
    </section>
  );
}

function ActivityFeed({
  activity,
  profileUsername,
  emptyAction,
  emptyActionLabel,
}: {
  activity: FriendActivity;
  profileUsername?: string;
  emptyAction?: () => void;
  emptyActionLabel?: string;
}) {
  const sentinelRef = useRef<HTMLDivElement | null>(null);
  const [bookshelfStatuses, setBookshelfStatuses] = useState<Map<string, BookshelfStatus>>(new Map());

  function updateActivityBookshelf(entry: BookshelfEntry) {
    setBookshelfStatuses((current) => new Map(current).set(entry.document.uuid, entry.status));
  }

  function openActivityDocument(item: FriendFeedItem) {
    const friendHighlights = item.activity_type === 'highlighted' && item.highlight_quotes.length > 0
      ? { username: item.person.username, quotes: item.highlight_quotes }
      : null;
    navigateTo(documentPath(item.document.uuid), { state: friendHighlights ? { friendHighlights } : null });
  }

  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel || !activity.hasMore || activity.loading || activity.loadingMore) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) activity.loadMore();
      },
      { rootMargin: '240px 0px' },
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [activity.hasMore, activity.loading, activity.loadingMore, activity.loadMore]);

  if (activity.loading) return <PeopleSkeleton />;

  if (activity.items.length === 0) {
    return (
      <div className="grid min-h-[26rem] place-items-center content-center gap-3 px-6 py-16 text-center">
        <span className="grid size-10 place-items-center rounded-full bg-muted text-muted-foreground"><BookOpen size={18} /></span>
        <strong className="font-medium">No reading activity yet</strong>
        <p className="max-w-xs text-sm text-muted-foreground">
          {profileUsername ? `@${profileUsername} has no saved or read pages to show yet.` : 'Pages your friends save or finish will appear here.'}
        </p>
        {emptyAction && emptyActionLabel && <Button uiVariant="outline" onClick={emptyAction}>{emptyActionLabel}</Button>}
      </div>
    );
  }

  return (
    <div className="divide-y">
      {activity.items.map((item) => (
        <article className="group px-2 py-3 hover:bg-muted/50" key={item.activity_id}>
          <div className="flex min-w-0 items-start gap-2">
            <button className="min-w-0 flex-1 truncate text-left text-sm font-medium text-foreground hover:underline" type="button" onClick={() => openActivityDocument(item)}>
              {item.document.title || item.document.url}
            </button>
            <DocumentActionsMenu
              documentUuid={item.document.uuid}
              status={bookshelfStatuses.get(item.document.uuid) ?? item.document.bookshelf_status}
              revealOnHover
              onBookshelfChange={updateActivityBookshelf}
            />
          </div>
          <div className="mt-1 flex min-w-0 flex-wrap items-center gap-x-1 text-xs text-muted-foreground">
            <span className="mr-0.5 inline-flex size-4 items-center justify-center text-foreground" aria-hidden="true">
              {activityIcon(item.activity_type)}
            </span>
            <button className="font-medium text-foreground hover:underline" type="button" onClick={() => openPeopleProfile(item.person.username)}>
              @{item.person.username}
            </button>
            <span>{activityLabel(item)}</span>
            <span aria-hidden="true">·</span>
            <span className="max-w-52 truncate" title={item.document.source_domain}>{item.document.source_domain}</span>
            <span aria-hidden="true">·</span>
            <time dateTime={item.activity_at}>{formatDate(item.activity_at)}</time>
          </div>
        </article>
      ))}
      {activity.hasMore ? (
        <div ref={sentinelRef} className="grid min-h-16 place-items-center py-4">
          {activity.loadingMore && <Loader2 className="animate-spin text-muted-foreground" size={17} />}
        </div>
      ) : (
        <div className="px-4 py-8 text-center text-sm text-muted-foreground">You made it to the beginning. Fresh reads from here on out.</div>
      )}
    </div>
  );
}

type FriendActivity = {
  items: FriendFeedItem[];
  loading: boolean;
  loadingMore: boolean;
  hasMore: boolean;
  error: string | null;
  reload: () => Promise<void>;
  loadMore: () => Promise<void>;
};

function useFriendActivity(username: string | null, enabled = true): FriendActivity {
  const [items, setItems] = useState<FriendFeedItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestIdRef = useRef(0);

  const reload = useCallback(async () => {
    const requestId = ++requestIdRef.current;
    if (!enabled) {
      setItems([]);
      setTotal(0);
      setLoading(false);
      setLoadingMore(false);
      setError(null);
      return;
    }
    setLoading(true);
    setLoadingMore(false);
    setError(null);
    try {
      const page = await getFriendsFeed({ limit: FEED_PAGE_SIZE, offset: 0, username: username ?? undefined });
      if (requestId !== requestIdRef.current) return;
      setItems(page.items);
      setTotal(page.total);
    } catch (err) {
      if (requestId === requestIdRef.current) {
        setItems([]);
        setTotal(0);
        setError(errorMessage(err));
      }
    } finally {
      if (requestId === requestIdRef.current) setLoading(false);
    }
  }, [enabled, username]);

  useEffect(() => {
    reload();
  }, [reload]);

  const loadMore = useCallback(async () => {
    if (!enabled || loading || loadingMore || items.length >= total) return;
    const requestId = requestIdRef.current;
    setLoadingMore(true);
    setError(null);
    try {
      const page = await getFriendsFeed({ limit: FEED_PAGE_SIZE, offset: items.length, username: username ?? undefined });
      if (requestId !== requestIdRef.current) return;
      setItems((current) => dedupeActivity([...current, ...page.items]));
      setTotal(page.total);
    } catch (err) {
      if (requestId === requestIdRef.current) setError(errorMessage(err));
    } finally {
      if (requestId === requestIdRef.current) setLoadingMore(false);
    }
  }, [enabled, items.length, loading, loadingMore, total, username]);

  return {
    items,
    loading,
    loadingMore,
    hasMore: items.length < total,
    error,
    reload,
    loadMore,
  };
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
          <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-2 rounded-md px-2 py-2 hover:bg-muted/50" key={friendship.id}>
            <strong className="min-w-0 truncate text-sm">@{friendship.person.username}</strong>
            <span className="flex items-center gap-1">
              {primaryLabel && onPrimary && (
                <Button className="size-8" uiVariant="ghost" size="icon" disabled={busy} aria-label={primaryLabel} title={primaryLabel} onClick={() => onPrimary(friendship.id)}>
                  <Check size={15} />
                </Button>
              )}
              <Button className="size-8" uiVariant="ghost" size="icon" disabled={busy} aria-label={secondaryLabel} title={secondaryLabel} onClick={() => onSecondary(friendship.id)}>
                {primaryLabel ? <Minus size={15} /> : <X size={15} />}
              </Button>
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}

function activityLabel(item: FriendFeedItem) {
  if (item.activity_type === 'favorited') return 'favorited';
  if (item.activity_type === 'read_later') return 'saved for later';
  if (item.activity_type === 'noted') return 'added a note';
  const count = item.highlight_count || item.highlight_quotes.length || 1;
  return `${count} ${count === 1 ? 'highlight' : 'highlights'}`;
}

function activityIcon(value: FriendFeedItem['activity_type']) {
  if (value === 'favorited') return <Heart size={13} strokeWidth={1.8} />;
  if (value === 'read_later') return <Clock3 size={13} strokeWidth={1.8} />;
  if (value === 'noted') return <Pencil size={13} strokeWidth={1.8} />;
  return <Highlighter size={13} strokeWidth={1.8} />;
}

function openPeopleProfile(username: string) {
  navigateTo(peopleProfilePath(username));
}

function dedupeActivity(items: FriendFeedItem[]) {
  const seen = new Set<string>();
  return items.filter((item) => {
    const key = item.activity_id;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
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
    <div className="divide-y" aria-label="Loading people activity">
      {[0, 1, 2].map((item) => (
        <div className="grid grid-cols-[minmax(0,1fr)] gap-2.5 py-3 sm:grid-cols-[minmax(0,1fr)_10rem]" key={item}>
          <span className="h-10 animate-pulse rounded bg-muted" />
          <span className="hidden h-8 animate-pulse rounded bg-muted sm:block" />
        </div>
      ))}
    </div>
  );
}

function NetworkSkeleton() {
  return (
    <div className="grid gap-2 py-4" aria-label="Loading network">
      <span className="h-9 animate-pulse rounded bg-muted" />
      <span className="h-9 animate-pulse rounded bg-muted" />
      <span className="h-9 animate-pulse rounded bg-muted" />
    </div>
  );
}

function ProfileSkeleton() {
  return (
    <div className="grid gap-3" aria-label="Loading profile">
      <span className="h-8 w-48 animate-pulse rounded bg-muted" />
      <span className="h-20 animate-pulse rounded bg-muted" />
    </div>
  );
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : 'Something went wrong';
}
