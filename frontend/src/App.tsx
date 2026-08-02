import { ReactNode, useEffect, useRef, useState } from 'react';
import { BookOpen, LibraryBig, LogOut, Moon, Orbit, PanelLeftClose, Search, Settings, Sun, UserCircle, Users } from 'lucide-react';
import { AuthGate } from './auth';
import { BookshelfView } from './views/BookshelfView';
import { DirectoryHub } from './views/DirectoryHub';
import { ExploreView } from './views/ExploreView';
import { PeopleView } from './views/PeopleView';
import { ProfileView } from './views/ProfileView';
import { SearchView } from './views/SearchView';
import { documentParentPath, documentPath, documentUuidFromPath, initialView, navigateTo, peopleUsernameFromPath, profileTargetFromPath, VIEW_STORAGE_KEY, viewFromPath, viewPaths, type ProfileTarget, type View } from './app/navigation';
import { DocumentRouteArtifact, DocumentRouteDrawer } from './components/DocumentRouteDrawer';
import { AppShell, Sidebar, Workspace } from './layout';
import { Button } from './components/ui';
import { IrisMark } from './components/IrisMark';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from './components/ui/dropdown-menu';
import type { User as IrisUser } from './types';

const THEME_STORAGE_KEY = 'iris.theme';
const SIDEBAR_STORAGE_KEY = 'iris.sidebarCollapsed';
type ThemeMode = 'light' | 'dark';

function initialTheme(): ThemeMode {
  if (typeof document === 'undefined') return 'light';
  const saved = window.localStorage.getItem(THEME_STORAGE_KEY);
  if (saved === 'dark' || saved === 'light') return saved;
  return document.documentElement.classList.contains('dark') ? 'dark' : 'light';
}

function initialSidebarCollapsed() {
  return typeof window !== 'undefined' && window.localStorage.getItem(SIDEBAR_STORAGE_KEY) === 'true';
}

function IrisApp({ currentUser, onSignOut }: { currentUser: IrisUser | null; onSignOut: () => void }) {
  const [view, setView] = useState<View>(initialView);
  const [profileTarget, setProfileTarget] = useState<ProfileTarget>(() =>
    typeof window === 'undefined'
      ? null
      : profileTargetFromPath(window.location.pathname, window.location.search),
  );
  const [documentUuid, setDocumentUuid] = useState<string | null>(() =>
    typeof window === 'undefined' ? null : documentUuidFromPath(window.location.pathname),
  );
  const [documentReason, setDocumentReason] = useState<string | null>(() =>
    typeof window === 'undefined' ? null : readDocumentReason(window.history.state),
  );
  const [friendHighlights, setFriendHighlights] = useState<FriendHighlightsContext | null>(() =>
    typeof window === 'undefined' ? null : readFriendHighlights(window.history.state),
  );
  const [profileUsername, setProfileUsername] = useState(currentUser?.username ?? null);
  const [themeMode, setThemeMode] = useState<ThemeMode>(initialTheme);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(initialSidebarCollapsed);
  const [navigationDrawerOpen, setNavigationDrawerOpen] = useState(false);
  const [navigationDrawerClosing, setNavigationDrawerClosing] = useState(false);
  const [wideWorkspace, setWideWorkspace] = useState(() =>
    typeof window !== 'undefined' && window.matchMedia('(min-width: 1024px)').matches,
  );
  const applyingPopState = useRef(false);
  const navigationDrawerTimerRef = useRef<number | null>(null);

  useEffect(() => {
    if (documentUuid !== null) return;
    window.localStorage.setItem(VIEW_STORAGE_KEY, view);
    let nextPath = viewPaths[view];
    if (view === 'directory') {
      nextPath = profileTarget?.domain
        ? `/directory/${encodeURIComponent(profileTarget.domain)}`
        : '/directory';
    } else if (view === 'people' && peopleUsernameFromPath(window.location.pathname)) {
      nextPath = window.location.pathname;
    }
    const currentPath = view === 'directory'
      ? `${window.location.pathname}${window.location.search}`
      : window.location.pathname;
    if (currentPath !== nextPath) {
      if (applyingPopState.current) {
        window.history.replaceState(null, '', nextPath);
      } else {
        window.history.pushState(null, '', nextPath);
      }
    }
    applyingPopState.current = false;
  }, [view, profileTarget?.domain]);

  useEffect(() => {
    function handlePopState() {
      const nextDocumentUuid = documentUuidFromPath(window.location.pathname);
      setDocumentUuid(nextDocumentUuid);
      setDocumentReason(nextDocumentUuid === null ? null : readDocumentReason(window.history.state));
      setFriendHighlights(nextDocumentUuid === null ? null : readFriendHighlights(window.history.state));
      const nextView = viewFromPath(window.location.pathname) ?? 'search';
      setProfileTarget(profileTargetFromPath(window.location.pathname, window.location.search));
      applyingPopState.current = true;
      setView(nextView);
    }
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  useEffect(() => {
    setProfileUsername(currentUser?.username ?? null);
  }, [currentUser?.username]);

  useEffect(() => {
    document.documentElement.classList.toggle('dark', themeMode === 'dark');
    window.localStorage.setItem(THEME_STORAGE_KEY, themeMode);
    window.dispatchEvent(new CustomEvent('iris-theme-change', { detail: themeMode }));
  }, [themeMode]);

  useEffect(() => {
    const query = window.matchMedia('(min-width: 1024px)');
    const updateWorkspaceWidth = (event: MediaQueryListEvent) => setWideWorkspace(event.matches);
    setWideWorkspace(query.matches);
    query.addEventListener('change', updateWorkspaceWidth);
    return () => query.removeEventListener('change', updateWorkspaceWidth);
  }, []);

  useEffect(() => {
    window.localStorage.setItem(SIDEBAR_STORAGE_KEY, String(sidebarCollapsed));
  }, [sidebarCollapsed]);

  useEffect(() => {
    if (documentUuid === null) {
      if (navigationDrawerTimerRef.current !== null) window.clearTimeout(navigationDrawerTimerRef.current);
      setNavigationDrawerOpen(false);
      setNavigationDrawerClosing(false);
    }
  }, [documentUuid]);

  useEffect(() => {
    if (documentUuid !== null && wideWorkspace) {
      setSidebarCollapsed(true);
    }
  }, [documentUuid, wideWorkspace]);

  useEffect(() => () => {
    if (navigationDrawerTimerRef.current !== null) window.clearTimeout(navigationDrawerTimerRef.current);
  }, []);

  function openNavigationDrawer() {
    if (navigationDrawerTimerRef.current !== null) window.clearTimeout(navigationDrawerTimerRef.current);
    setNavigationDrawerClosing(false);
    setNavigationDrawerOpen(true);
  }

  function closeNavigationDrawer() {
    if (!navigationDrawerOpen || navigationDrawerClosing) return;
    setNavigationDrawerClosing(true);
    navigationDrawerTimerRef.current = window.setTimeout(() => {
      setNavigationDrawerOpen(false);
      setNavigationDrawerClosing(false);
      navigationDrawerTimerRef.current = null;
    }, 210);
  }

  function openProfile(sourceId: number, domain: string) {
    setDocumentUuid(null);
    setProfileTarget({ sourceId, domain });
    setView('directory');
  }

  function openDirectoryRoot() {
    setDocumentUuid(null);
    setProfileTarget(null);
    setView('directory');
  }

  function closeDocumentDrawer() {
    navigateTo(`${documentParentPath(window.location.pathname)}${window.location.search}`, { replace: true });
  }

  function openSearchDocument(documentUuid: string, reason: string) {
    navigateTo(documentPath(documentUuid), { state: { documentReason: reason } });
  }

  const navItems: Array<{ view: View; label: string; icon: ReactNode }> = [
    { view: 'search', label: 'Search', icon: <Search size={15} /> },
    { view: 'bookshelf', label: 'Bookshelf', icon: <BookOpen size={15} /> },
    { view: 'people', label: 'People', icon: <Users size={15} /> },
    { view: 'explore', label: 'Explore', icon: <Orbit size={15} /> },
    { view: 'directory', label: 'Directory', icon: <LibraryBig size={15} /> },
  ];
  const documentArtifactOpen = documentUuid !== null && wideWorkspace;
  const focusedDirectory = view === 'directory' && profileTarget !== null;
  const navigationCollapsed = documentArtifactOpen ? !navigationDrawerOpen : sidebarCollapsed;
  const navigationIsDrawer = !focusedDirectory && documentArtifactOpen && navigationDrawerOpen;
  const shellLayout = documentArtifactOpen
    ? focusedDirectory
      ? 'md:grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(24rem,42vw)]'
      : 'lg:grid-cols-[3.5rem_minmax(0,1fr)_minmax(24rem,42vw)]'
    : focusedDirectory
      ? 'md:grid-cols-1'
    : sidebarCollapsed
      ? 'md:grid-cols-[3.5rem_minmax(0,1fr)]'
      : undefined;

  return (
    <AppShell className={shellLayout}>
      {navigationIsDrawer && (
        <button
          className={`fixed inset-0 z-40 hidden bg-black/20 transition-opacity duration-200 motion-reduce:transition-none lg:block ${navigationDrawerClosing ? 'opacity-0' : 'animate-in fade-in-0 opacity-100'}`}
          type="button"
          aria-label="Close navigation"
          onClick={closeNavigationDrawer}
        />
      )}
      {!focusedDirectory && <Sidebar className={navigationIsDrawer ? `transition-[transform,opacity] duration-200 ease-out motion-reduce:transition-none lg:z-50 lg:w-52 lg:shadow-xl ${navigationDrawerClosing ? 'lg:-translate-x-full lg:opacity-0' : 'lg:animate-in lg:slide-in-from-left-full lg:opacity-100'}` : undefined}>
        <div className={`flex h-14 shrink-0 items-center text-lg font-semibold tracking-tight md:h-16 ${navigationCollapsed ? 'px-4 md:justify-center md:px-0' : 'justify-between pl-4 pr-2'}`}>
          {navigationCollapsed ? (
            <>
              <span className="flex items-center gap-2 md:hidden"><IrisMark />iris</span>
              <button
                className="hidden size-9 place-items-center rounded-md hover:bg-sidebar-accent md:grid"
                type="button"
                onClick={() => {
                  if (documentArtifactOpen) openNavigationDrawer();
                  else setSidebarCollapsed(false);
                }}
                aria-label="Open navigation"
                title="Open navigation"
              >
                <IrisMark className="size-7" />
              </button>
            </>
          ) : (
            <>
              <span className="flex items-center gap-2"><IrisMark className="size-7 shrink-0" />iris</span>
              <button
                className="hidden size-8 place-items-center rounded-md text-muted-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground md:grid"
                type="button"
                onClick={() => {
                  if (documentArtifactOpen) closeNavigationDrawer();
                  else setSidebarCollapsed(true);
                }}
                aria-label="Collapse navigation"
                title="Collapse navigation"
              >
                <PanelLeftClose size={16} />
              </button>
            </>
          )}
        </div>
        <nav className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto px-2 pb-2 md:block md:space-y-1 md:overflow-visible">
          {navItems.map((item) => (
            <Button
              key={item.view}
              type="button"
              onClick={() => {
                setDocumentUuid(null);
                if (item.view === 'directory') {
                  openDirectoryRoot();
                } else if (item.view === 'people') {
                  navigateTo('/people');
                } else {
                  setView(item.view);
                }
              }}
              uiVariant="nav"
              className={`w-auto md:w-full ${navigationCollapsed ? 'md:justify-center md:px-0' : ''}`}
              data-active={view === item.view ? 'true' : undefined}
              title={navigationCollapsed ? item.label : undefined}
            >
              {item.icon}
              <span className={navigationCollapsed ? 'md:hidden' : ''}>{item.label}</span>
            </Button>
          ))}
        </nav>
        {currentUser && (
          <div className="hidden border-t p-2 md:block">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button uiVariant="nav" className={`h-auto w-full justify-start py-2 ${navigationCollapsed ? 'md:justify-center md:px-0' : ''}`} title={navigationCollapsed ? 'Settings' : undefined}>
                  <Settings size={17} />
                  <span className={`min-w-0 flex-1 truncate text-left ${navigationCollapsed ? 'md:hidden' : ''}`}>
                    <span className="block">Settings</span>
                    <span className="block truncate text-xs font-normal text-muted-foreground">
                      {profileUsername ? `@${profileUsername}` : currentUser.email}
                    </span>
                  </span>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent side="right" align="end" className="w-56">
                <DropdownMenuLabel className="truncate">{currentUser.email}</DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem onSelect={() => {
                  setDocumentUuid(null);
                  setView('profile');
                }}>
                  <UserCircle />
                  My profile
                </DropdownMenuItem>
                <DropdownMenuItem onSelect={() => setThemeMode((mode) => (mode === 'dark' ? 'light' : 'dark'))}>
                  {themeMode === 'dark' ? <Sun /> : <Moon />}
                  {themeMode === 'dark' ? 'Light mode' : 'Dark mode'}
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem variant="destructive" onSelect={onSignOut}>
                  <LogOut />
                  Log out
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        )}
      </Sidebar>}
      <Workspace view={view}>
        {view === 'search' && (
          <SearchView
            selectedDocumentUuid={documentUuid}
            onOpenDocument={openSearchDocument}
            artifactOpen={documentArtifactOpen}
            greetingName={searchGreetingName(currentUser?.display_name, currentUser?.email)}
          />
        )}
        {view === 'bookshelf' && <BookshelfView onDiscover={() => {
          setDocumentUuid(null);
          setView('search');
        }} />}
        {view === 'people' && <PeopleView />}
        {view === 'explore' && <ExploreView />}
        {view === 'profile' && <ProfileView onUsernameChange={setProfileUsername} />}
        {view === 'directory' && (
          <DirectoryHub
            target={profileTarget}
            onOpenProfile={openProfile}
            onDirectoryRoot={openDirectoryRoot}
          />
        )}
      </Workspace>
      {documentArtifactOpen && documentUuid !== null && (
        <DocumentRouteArtifact key={documentUuid} documentUuid={documentUuid} reason={documentReason} friendHighlights={friendHighlights} onClose={closeDocumentDrawer} />
      )}
      {documentUuid !== null && !documentArtifactOpen && <DocumentRouteDrawer key={documentUuid} documentUuid={documentUuid} reason={documentReason} friendHighlights={friendHighlights} onClose={closeDocumentDrawer} />}
    </AppShell>
  );
}

function searchGreetingName(displayName?: string | null, email?: string) {
  const accountFirstName = displayName?.trim().split(/\s+/)[0];
  const source = accountFirstName || email?.split('@')[0] || '';
  const firstName = source.split(/[-_.\s]+/)[0]?.trim();
  return firstName ? firstName.charAt(0).toUpperCase() + firstName.slice(1) : null;
}

function readDocumentReason(state: unknown): string | null {
  if (!state || typeof state !== 'object' || !('documentReason' in state)) return null;
  const reason = (state as { documentReason?: unknown }).documentReason;
  return typeof reason === 'string' && reason.trim() ? reason : null;
}

type FriendHighlightsContext = { username: string; quotes: string[] };

function readFriendHighlights(state: unknown): FriendHighlightsContext | null {
  if (!state || typeof state !== 'object' || !('friendHighlights' in state)) return null;
  const value = (state as { friendHighlights?: unknown }).friendHighlights;
  if (!value || typeof value !== 'object') return null;
  const username = 'username' in value ? (value as { username?: unknown }).username : null;
  const quotes = 'quotes' in value ? (value as { quotes?: unknown }).quotes : null;
  if (typeof username !== 'string' || !Array.isArray(quotes)) return null;
  const cleanQuotes = quotes.filter((quote): quote is string => typeof quote === 'string' && Boolean(quote.trim()));
  return cleanQuotes.length > 0 ? { username, quotes: cleanQuotes } : null;
}

export default function App() {
  return (
    <AuthGate>
      {(currentUser, onSignOut) => <IrisApp currentUser={currentUser} onSignOut={onSignOut} />}
    </AuthGate>
  );
}
