import { type FormEvent, type ReactNode, useEffect, useState } from 'react';
import { onAuthStateChanged, signInWithPopup, signOut, type User as FirebaseUser } from 'firebase/auth';
import { ArrowRight, BarChart3, Bookmark, ExternalLink, Folder, Heart, LogOut, MessageSquareText, RefreshCw, Search, StickyNote, Users, X } from 'lucide-react';
import { getConversation, getMe, getOverview, getQueries, getUserLibrary, getUsers } from './api';
import { IrisMark } from './components/IrisMark';
import { Button } from './components/ui/button';
import { auth, firebaseEnabled, googleProvider } from './firebase';
import { cn } from './lib/utils';
import type { AdminConversation, AdminLibraryEntry, AdminOverview, AdminQuery, AdminUser, AdminUserLibrary, IrisUser, Page } from './types';

type View = 'overview' | 'queries' | 'users';
const emptyPage = <T,>(): Page<T> => ({ items: [], total: 0, limit: 50, offset: 0, has_next: false, has_previous: false });
const tableClass = 'w-full min-w-[760px] border-collapse text-sm [&_th]:border-b [&_th]:bg-muted/40 [&_th]:px-4 [&_th]:py-2 [&_th]:text-left [&_th]:text-xs [&_th]:font-semibold [&_th]:uppercase [&_th]:text-muted-foreground [&_td]:border-b [&_td]:px-4 [&_td]:py-3 [&_td]:align-top [&_tbody_tr:last-child_td]:border-b-0 [&_tbody_tr:hover]:bg-muted/30';

function Shell({ user, onSignOut }: { user: IrisUser; onSignOut: () => void }) {
  const [view, setView] = useState<View>('overview');
  const [queryUserId, setQueryUserId] = useState<number>();
  const navItems: Array<{ id: View; label: string; icon: ReactNode }> = [
    { id: 'overview', label: 'Overview', icon: <BarChart3 size={15} /> },
    { id: 'queries', label: 'Queries', icon: <MessageSquareText size={15} /> },
    { id: 'users', label: 'Users', icon: <Users size={15} /> },
  ];

  return (
    <main className="grid min-h-svh grid-cols-1 bg-background md:grid-cols-[13rem_minmax(0,1fr)]">
      <aside className="sticky top-0 z-30 flex h-auto border-b bg-sidebar text-sidebar-foreground md:h-svh md:flex-col md:border-r md:border-b-0">
        <div className="flex h-14 shrink-0 items-center gap-2 px-4 text-lg font-semibold tracking-tight md:h-16">
          <IrisMark className="size-7" />
          <span>iris</span>
          <span className="text-xs font-medium text-muted-foreground">admin</span>
        </div>
        <nav className="flex flex-1 items-center gap-1 overflow-x-auto px-2 pb-2 md:block md:space-y-1 md:overflow-visible">
          {navItems.map((item) => (
            <Button
              key={item.id}
              uiVariant="nav"
              data-active={view === item.id ? 'true' : undefined}
              onClick={() => setView(item.id)}
            >
              {item.icon}
              {item.label}
            </Button>
          ))}
        </nav>
        <div className="hidden border-t p-2 md:block">
          <p className="truncate px-2 py-1 text-xs text-muted-foreground">{user.email}</p>
          <Button uiVariant="nav" onClick={onSignOut}><LogOut size={15} />Log out</Button>
        </div>
      </aside>
      <section className="min-h-svh min-w-0 overflow-x-hidden">
        {view === 'overview' && <OverviewPage onOpenQueries={() => setView('queries')} onOpenUsers={() => setView('users')} />}
        {view === 'queries' && <QueriesPage userId={queryUserId} onClearUser={() => setQueryUserId(undefined)} />}
        {view === 'users' && <UsersPage onViewQueries={(userId) => { setQueryUserId(userId); setView('queries'); }} />}
      </section>
    </main>
  );
}

function PageHeader({ eyebrow, title, description, action }: { eyebrow?: string; title: string; description: string; action?: ReactNode }) {
  return (
    <header className="mb-6 flex items-start justify-between gap-4">
      <div>
        {eyebrow && <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{eyebrow}</p>}
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{description}</p>
      </div>
      {action}
    </header>
  );
}

function OverviewPage({ onOpenQueries, onOpenUsers }: { onOpenQueries: () => void; onOpenUsers: () => void }) {
  const [overview, setOverview] = useState<AdminOverview>();
  const [queries, setQueries] = useState<Page<AdminQuery>>(emptyPage);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();

  async function load() {
    setLoading(true);
    setError(undefined);
    try {
      const [nextOverview, nextQueries] = await Promise.all([
        getOverview(),
        getQueries({ limit: 8, offset: 0 }),
      ]);
      setOverview(nextOverview);
      setQueries(nextQueries);
    } catch (err) {
      setError(readError(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []);
  const metrics = [
    ['Users', overview?.totals.users],
    ['Queries', overview?.totals.queries],
    ['Conversations', overview?.totals.conversations],
    ['Saved documents', overview?.totals.saved_documents],
    ['Sources', overview?.totals.sources],
    ['Documents', overview?.totals.documents],
  ] as const;

  return (
    <div className="mx-auto max-w-[90rem] p-4 sm:p-6">
      <PageHeader title="Overview" description="The top-level shape of Iris right now." action={<Button onClick={load}><RefreshCw size={15} />Refresh</Button>} />
      {error && <Notice tone="error">{error}</Notice>}
      <div className="grid border-y sm:grid-cols-3 xl:grid-cols-6">
        {metrics.map(([label, value], index) => {
          const content = <><span className="text-xs font-medium uppercase text-muted-foreground">{label}</span><strong className="mt-1 block text-2xl font-semibold leading-tight">{typeof value === 'number' ? value.toLocaleString() : '—'}</strong></>;
          const className = `min-w-0 px-4 py-5 text-left ${index > 0 ? 'border-t sm:border-t-0 sm:border-l' : ''}`;
          if (label === 'Users') return <button key={label} type="button" className={`${className} transition-colors hover:bg-muted/40`} onClick={onOpenUsers}>{content}</button>;
          if (label === 'Queries' || label === 'Conversations') return <button key={label} type="button" className={`${className} transition-colors hover:bg-muted/40`} onClick={onOpenQueries}>{content}</button>;
          return <div key={label} className={className}>{content}</div>;
        })}
      </div>

      <section className="mt-10">
        <div className="mb-3 flex items-end justify-between gap-4">
          <div><p className="text-xs font-semibold uppercase text-muted-foreground">Latest activity</p><h2 className="mt-1 text-lg font-semibold">Recent queries</h2></div>
          <Button uiVariant="rowAction" onClick={onOpenQueries}>View all <ArrowRight size={14} /></Button>
        </div>
        <div className="border-y">
          {queries.items.map((query) => (
            <button key={query.id} type="button" className="grid w-full gap-2 border-b px-4 py-3 text-left last:border-0 hover:bg-muted/30 md:grid-cols-[minmax(0,1fr)_14rem_8rem]" onClick={onOpenQueries}>
              <span className="truncate text-sm font-medium">{query.content}</span>
              <span className="truncate text-sm text-muted-foreground">{query.username ? `@${query.username}` : query.email}</span>
              <span className="text-sm text-muted-foreground md:text-right">{formatDate(query.created_at)}</span>
            </button>
          ))}
          {!loading && queries.items.length === 0 && <Notice>No queries yet.</Notice>}
          {loading && <Notice>Loading overview…</Notice>}
        </div>
      </section>
    </div>
  );
}

function QueriesPage({ userId, onClearUser }: { userId?: number; onClearUser: () => void }) {
  const [page, setPage] = useState<Page<AdminQuery>>(emptyPage);
  const [query, setQuery] = useState('');
  const [appliedQuery, setAppliedQuery] = useState('');
  const [conversation, setConversation] = useState<AdminConversation | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();

  async function load(offset = 0) {
    setLoading(true);
    setError(undefined);
    try { setPage(await getQueries({ q: appliedQuery, userId, limit: page.limit, offset })); }
    catch (err) { setError(readError(err)); }
    finally { setLoading(false); }
  }
  useEffect(() => { void load(0); }, [appliedQuery, userId]);
  async function inspect(uuid: string) {
    setError(undefined);
    try { setConversation(await getConversation(uuid)); }
    catch (err) { setError(readError(err)); }
  }
  function submit(event: FormEvent) { event.preventDefault(); setAppliedQuery(query.trim()); }

  return (
    <div className="mx-auto max-w-[90rem] p-4 sm:p-6">
      <PageHeader eyebrow="Search activity" title="Recent queries" description="Prompts, responses, retrieval steps, and inspected documents." action={<Button onClick={() => load(page.offset)}><RefreshCw size={15} />Refresh</Button>} />
      <form className="mb-4 flex items-center gap-2" onSubmit={submit}>
        <div className="relative max-w-xl flex-1"><Search className="absolute left-3 top-2.5 text-muted-foreground" size={16} /><input className="h-9 w-full rounded-md border bg-background pl-9 pr-3 text-sm" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search prompt, email, or username" /></div>
        <Button type="submit">Search</Button>
        {userId && <Button type="button" uiVariant="ghost" onClick={onClearUser}><X size={14} />Clear user</Button>}
      </form>
      {error && <Notice tone="error">{error}</Notice>}
      <Pager page={page} onPage={(offset) => load(offset)} />
      <div className="overflow-x-auto border-y"><table className={tableClass}><thead><tr><th>Query</th><th>User</th><th>Trace</th><th>Time</th></tr></thead><tbody>{page.items.map((item) => <tr key={item.id} className="cursor-pointer" onClick={() => inspect(item.conversation_uuid)}><td className="max-w-2xl"><p className="font-medium">{item.content}</p>{item.answer_preview && <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{item.answer_preview}</p>}</td><td><p>{item.username ? `@${item.username}` : item.email}</p>{item.username && <p className="text-xs text-muted-foreground">{item.email}</p>}</td><td>{item.step_count} steps · {item.result_count} results</td><td className="whitespace-nowrap text-muted-foreground">{formatDate(item.created_at)}</td></tr>)}</tbody></table>{!loading && page.items.length === 0 && <Notice>No queries found.</Notice>}</div>
      {loading && <Notice>Loading queries…</Notice>}
      {conversation && <ConversationPanel conversation={conversation} onClose={() => setConversation(null)} />}
    </div>
  );
}

function UsersPage({ onViewQueries }: { onViewQueries: (userId: number) => void }) {
  const [page, setPage] = useState<Page<AdminUser>>(emptyPage);
  const [query, setQuery] = useState('');
  const [applied, setApplied] = useState('');
  const [selectedUser, setSelectedUser] = useState<AdminUser | null>(null);
  const [error, setError] = useState<string>();
  const [loading, setLoading] = useState(true);
  async function load(offset = 0) {
    setLoading(true);
    setError(undefined);
    try { setPage(await getUsers({ q: applied, limit: page.limit, offset })); }
    catch (err) { setError(readError(err)); }
    finally { setLoading(false); }
  }
  useEffect(() => { void load(0); }, [applied]);

  return (
    <div className="mx-auto max-w-[90rem] p-4 sm:p-6">
      <PageHeader eyebrow="Profiles" title="Users" description="Open a user to generate a compact account and usage report." action={<Button onClick={() => load(page.offset)}><RefreshCw size={15} />Refresh</Button>} />
      <form className="mb-4 flex max-w-xl gap-2" onSubmit={(event) => { event.preventDefault(); setApplied(query.trim()); }}><input className="h-9 flex-1 rounded-md border bg-background px-3 text-sm" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search email or username" /><Button type="submit">Search</Button></form>
      {error && <Notice tone="error">{error}</Notice>}
      <Pager page={page} onPage={(offset) => load(offset)} />
      <div className="overflow-x-auto border-y"><table className={tableClass}><thead><tr><th>User</th><th>Joined</th><th>Chats</th><th>Queries</th><th>Saved</th><th></th></tr></thead><tbody>{page.items.map((user) => <tr key={user.id} className="cursor-pointer" onClick={() => setSelectedUser(user)}><td><p className="font-medium">{user.username ? `@${user.username}` : 'No username'}</p><p className="text-xs text-muted-foreground">{user.email}</p></td><td>{formatDate(user.created_at)}</td><td>{user.conversation_count}</td><td>{user.query_count}</td><td>{user.saved_document_count}</td><td><Button uiVariant="rowAction" onClick={(event) => { event.stopPropagation(); setSelectedUser(user); }}>View report</Button></td></tr>)}</tbody></table>{!loading && page.items.length === 0 && <Notice>No users found.</Notice>}</div>
      {loading && <Notice>Loading users…</Notice>}
      {selectedUser && <UserReportPanel user={selectedUser} onClose={() => setSelectedUser(null)} onViewQueries={onViewQueries} />}
    </div>
  );
}

function UserReportPanel({ user, onClose, onViewQueries }: { user: AdminUser; onClose: () => void; onViewQueries: (userId: number) => void }) {
  const [queries, setQueries] = useState<Page<AdminQuery>>(emptyPage);
  const [library, setLibrary] = useState<AdminUserLibrary>();
  const [queryError, setQueryError] = useState<string>();
  const [libraryError, setLibraryError] = useState<string>();
  useEffect(() => {
    let active = true;
    setQueries(emptyPage());
    setLibrary(undefined);
    setQueryError(undefined);
    setLibraryError(undefined);
    Promise.allSettled([
      getQueries({ userId: user.id, limit: 10, offset: 0 }),
      getUserLibrary(user.id, { limit: 50, offset: 0 }),
    ]).then(([queryResult, libraryResult]) => {
      if (!active) return;
      if (queryResult.status === 'fulfilled') setQueries(queryResult.value);
      else setQueryError(readError(queryResult.reason));
      if (libraryResult.status === 'fulfilled') setLibrary(libraryResult.value);
      else setLibraryError(readError(libraryResult.reason));
    });
    return () => { active = false; };
  }, [user.id]);
  async function pageLibrary(offset: number) {
    setLibraryError(undefined);
    try { setLibrary(await getUserLibrary(user.id, { limit: library?.entries.limit ?? 50, offset })); }
    catch (err) { setLibraryError(readError(err)); }
  }
  const metrics = [['Chats', user.conversation_count], ['Queries', user.query_count], ['Saved', user.saved_document_count]] as const;
  return (
    <Drawer onClose={onClose} title={user.username ? `@${user.username}` : user.email} subtitle={user.username ? user.email : 'User report'}>
      <dl className="grid grid-cols-2 border-y text-sm"><div className="p-4"><dt className="text-xs uppercase text-muted-foreground">Joined</dt><dd className="mt-1">{formatDate(user.created_at)}</dd></div><div className="border-l p-4"><dt className="text-xs uppercase text-muted-foreground">Onboarding</dt><dd className="mt-1">{user.onboarding_completed_at ? 'Complete' : 'Incomplete'}</dd></div></dl>
      <div className="mt-6 grid grid-cols-3 border-y">{metrics.map(([label, value], index) => <div key={label} className={`p-4 ${index > 0 ? 'border-l' : ''}`}><p className="text-xs uppercase text-muted-foreground">{label}</p><p className="mt-1 text-2xl font-semibold">{value.toLocaleString()}</p></div>)}</div>
      <div className="mt-8 flex items-end justify-between"><div><p className="text-xs font-semibold uppercase text-muted-foreground">Activity sample</p><h3 className="mt-1 font-semibold">Recent queries</h3></div><Button uiVariant="rowAction" onClick={() => onViewQueries(user.id)}>View all <ArrowRight size={14} /></Button></div>
      {queryError && <Notice tone="error">Recent queries unavailable: {queryError}</Notice>}
      <div className="mt-3 border-y">{queries.items.map((query) => <div key={query.id} className="border-b px-3 py-3 last:border-0"><p className="text-sm font-medium">{query.content}</p><p className="mt-1 text-xs text-muted-foreground">{formatDate(query.created_at)} · {query.step_count} steps · {query.result_count} results</p></div>)}{queries.items.length === 0 && !queryError && <Notice>No recent queries.</Notice>}</div>
      <div className="mt-8 flex items-end justify-between gap-4"><div><p className="text-xs font-semibold uppercase text-muted-foreground">Organization</p><h3 className="mt-1 font-semibold">Collections</h3></div><span className="text-xs text-muted-foreground">{library?.collections.length ?? '—'}</span></div>
      {libraryError && <Notice tone="error">Library data unavailable: {libraryError}</Notice>}
      <div className="mt-3 border-y">
        {library?.collections.map((collection) => (
          <details key={collection.id} className="group border-b last:border-0">
            <summary className="flex cursor-pointer list-none items-center gap-3 px-3 py-3 hover:bg-muted/30">
              <Folder size={16} className="shrink-0 text-muted-foreground" />
              <span className="min-w-0 flex-1"><span className="block truncate text-sm font-medium">{collection.name}</span>{collection.description && <span className="mt-0.5 block truncate text-xs text-muted-foreground">{collection.description}</span>}</span>
              <span className="text-xs text-muted-foreground">{collection.items.length} {collection.items.length === 1 ? 'item' : 'items'} · {collection.visibility === 'share_link' ? 'Shared' : 'Private'}</span>
            </summary>
            <div className="border-t bg-muted/10 px-3">{collection.items.map((entry) => <LibraryEntryRow key={entry.document.uuid} entry={entry} compact />)}{collection.items.length === 0 && <Notice>Nothing in this collection.</Notice>}</div>
          </details>
        ))}
        {library && library.collections.length === 0 && <Notice>No collections.</Notice>}
        {!library && !libraryError && <Notice>Loading collections…</Notice>}
      </div>
      <div className="mt-8"><p className="text-xs font-semibold uppercase text-muted-foreground">Saved state</p><h3 className="mt-1 font-semibold">Library items</h3></div>
      {library && <Pager page={library.entries} onPage={pageLibrary} />}
      <div className="border-y">{library?.entries.items.map((entry) => <LibraryEntryRow key={entry.document.uuid} entry={entry} />)}{library && library.entries.items.length === 0 && <Notice>No saved items.</Notice>}{!library && !libraryError && <Notice>Loading library…</Notice>}</div>
    </Drawer>
  );
}

function LibraryEntryRow({ entry, compact = false }: { entry: AdminLibraryEntry; compact?: boolean }) {
  const detail = [entry.status, entry.favorited ? 'favorited' : null, ...entry.tags].filter(Boolean).join(' · ');
  return (
    <div className={cn('flex gap-3 border-b py-3 last:border-0', !compact && 'px-3')}>
      <Bookmark size={16} className="mt-0.5 shrink-0 text-muted-foreground" />
      <div className="min-w-0 flex-1">
        <a className="block truncate text-sm font-medium hover:text-primary" href={entry.document.url} target="_blank" rel="noreferrer">{entry.document.title || entry.document.url} <ExternalLink className="inline" size={12} /></a>
        <p className="mt-0.5 truncate text-xs text-muted-foreground">{entry.document.source_domain} · {detail}</p>
        {entry.note && <p className="mt-2 flex gap-2 text-xs leading-5"><StickyNote size={13} className="mt-0.5 shrink-0" />{entry.note}</p>}
        {entry.intent_note && <p className="mt-1 text-xs leading-5 text-muted-foreground">Intent: {entry.intent_note}</p>}
      </div>
      {entry.favorited && <Heart size={15} className="mt-0.5 shrink-0" aria-label="Favorited" />}
    </div>
  );
}

function ConversationPanel({ conversation, onClose }: { conversation: AdminConversation; onClose: () => void }) {
  return (
    <Drawer onClose={onClose} title={conversation.title || 'Conversation'} subtitle={`${conversation.username ? `@${conversation.username}` : conversation.email} · ${formatDate(conversation.created_at)}`}>
      <div className="space-y-6">{conversation.messages.map((message) => <article key={message.id} className={message.role === 'user' ? 'ml-10 rounded-lg bg-muted p-4' : ''}><p className="mb-2 text-xs font-semibold uppercase text-muted-foreground">{message.role}</p><p className="whitespace-pre-wrap text-sm leading-6">{message.content}</p>{message.steps.length > 0 && <details className="mt-4 border-y py-3"><summary className="cursor-pointer text-sm font-medium">Search process · {message.steps.length} steps</summary><div className="mt-3 space-y-2">{message.steps.map((step, index) => <pre key={index} className="overflow-x-auto whitespace-pre-wrap bg-muted p-2 text-xs">{JSON.stringify(step, null, 2)}</pre>)}</div></details>}{message.results.length > 0 && <details className="mt-2 border-y py-3"><summary className="cursor-pointer text-sm font-medium">Inspected documents · {message.results.length}</summary><ul className="mt-3 space-y-3">{message.results.map((result) => <li key={result.document_uuid}><a className="text-sm font-medium hover:text-primary" href={result.url} target="_blank" rel="noreferrer">{result.title || result.url} <ExternalLink className="inline" size={12} /></a><p className="text-xs text-muted-foreground">{result.source_domain} · {result.reason}</p></li>)}</ul></details>}</article>)}</div>
    </Drawer>
  );
}

function Drawer({ title, subtitle, onClose, children }: { title: string; subtitle: string; onClose: () => void; children: ReactNode }) {
  return <div className="fixed inset-0 z-40 flex justify-end bg-black/15" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><aside className="h-full w-full max-w-2xl overflow-y-auto border-l bg-background shadow-xl"><header className="sticky top-0 z-10 flex items-start justify-between border-b bg-background/95 p-5 backdrop-blur"><div><p className="font-semibold">{title}</p><p className="mt-1 text-xs text-muted-foreground">{subtitle}</p></div><Button size="icon" uiVariant="ghost" onClick={onClose} aria-label="Close"><X size={17} /></Button></header><div className="p-5">{children}</div></aside></div>;
}

function Pager<T>({ page, onPage }: { page: Page<T>; onPage: (offset: number) => void }) {
  return <div className="my-3 flex items-center justify-end gap-2 text-xs text-muted-foreground"><span className="mr-auto">{page.total === 0 ? 0 : page.offset + 1}–{Math.min(page.offset + page.items.length, page.total)} of {page.total}</span><Button disabled={!page.has_previous} onClick={() => onPage(Math.max(0, page.offset - page.limit))}>Previous</Button><Button disabled={!page.has_next} onClick={() => onPage(page.offset + page.limit)}>Next</Button></div>;
}
function Notice({ children, tone }: { children: ReactNode; tone?: 'error' }) { return <div className={`border-y px-4 py-3 text-sm ${tone === 'error' ? 'border-destructive/30 bg-destructive/10 text-destructive' : 'text-muted-foreground'}`}>{children}</div>; }
function formatDate(value?: string | null) { return value ? new Date(value).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }) : '—'; }
function readError(error: unknown) { return error instanceof Error ? error.message : 'Request failed'; }

export default function App() {
  const [firebaseUser, setFirebaseUser] = useState<FirebaseUser | null>(null);
  const [user, setUser] = useState<IrisUser | null>(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string>();
  useEffect(() => {
    if (!auth) {
      getMe().then(setUser).catch((err) => setError(readError(err))).finally(() => setReady(true));
      return;
    }
    return onAuthStateChanged(auth, (nextUser) => {
      setFirebaseUser(nextUser);
      setUser(null);
      setError(undefined);
      setReady(true);
      if (nextUser) getMe().then(setUser).catch((err) => setError(readError(err)));
    });
  }, []);

  if (!ready || (firebaseEnabled && firebaseUser && !user && !error)) return <div className="grid min-h-svh place-items-center text-sm text-muted-foreground">Loading…</div>;
  if (firebaseEnabled && (!firebaseUser || error)) return <div className="grid min-h-svh place-items-center p-6"><div className="w-full max-w-4xl"><div className="flex items-center gap-2 text-lg font-semibold"><IrisMark className="size-8" />iris</div><div className="mt-20 flex max-w-3xl items-center justify-between gap-8"><div><p className="text-xs font-semibold uppercase text-muted-foreground">Admin</p><h1 className="mt-2 text-3xl font-semibold tracking-tight">See what Iris is doing.</h1>{error && <p className="mt-3 text-sm text-destructive">{error}</p>}</div><Button size="icon" uiVariant="plainIcon" className="size-12" onClick={() => auth && signInWithPopup(auth, googleProvider).catch((err) => setError(readError(err)))} aria-label="Continue with Google"><ArrowRight size={28} /></Button></div></div></div>;
  if (!firebaseEnabled && error) return <div className="grid min-h-svh place-items-center p-6"><Notice tone="error">{error}</Notice></div>;
  if (!user) return <div className="grid min-h-svh place-items-center text-sm text-muted-foreground">Loading…</div>;
  if (!user.is_admin) return <div className="grid min-h-svh place-items-center p-6"><div className="max-w-md"><IrisMark className="mb-5 size-8" /><h1 className="text-lg font-semibold">Admin access required</h1><p className="mt-2 text-sm text-muted-foreground">{user.email} is not in IRIS_ADMIN_EMAILS.</p><Button className="mt-5" onClick={() => auth && signOut(auth)}>Sign out</Button></div></div>;
  return <Shell user={user} onSignOut={() => auth && void signOut(auth)} />;
}
