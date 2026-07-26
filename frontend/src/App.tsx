import { ReactNode, useEffect, useRef, useState } from 'react';
import { BookOpen, LayoutDashboard, LogOut, Moon, Orbit, Search, Settings, Sun, UserCircle, Users } from 'lucide-react';
import { AuthGate } from './auth';
import { AdminView } from './views/AdminView';
import { BookshelfView } from './views/BookshelfView';
import { DirectoryHub } from './views/DirectoryHub';
import { PeopleView } from './views/PeopleView';
import { ProfileView } from './views/ProfileView';
import { SearchView } from './views/SearchView';
import { documentParentPath, documentPath, documentUuidFromPath, initialView, navigateTo, profileTargetFromPath, VIEW_STORAGE_KEY, viewFromPath, viewPaths, type ProfileTarget, type View } from './app/navigation';
import { DocumentRouteDrawer } from './components/DocumentRouteDrawer';
import { AppShell, Sidebar, Workspace } from './layout';
import { Button } from './components/ui';
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
type ThemeMode = 'light' | 'dark';

function initialTheme(): ThemeMode {
  if (typeof document === 'undefined') return 'light';
  const saved = window.localStorage.getItem(THEME_STORAGE_KEY);
  if (saved === 'dark' || saved === 'light') return saved;
  return document.documentElement.classList.contains('dark') ? 'dark' : 'light';
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
  const [profileUsername, setProfileUsername] = useState(currentUser?.username ?? null);
  const [themeMode, setThemeMode] = useState<ThemeMode>(initialTheme);
  const applyingPopState = useRef(false);

  useEffect(() => {
    if (documentUuid !== null) return;
    window.localStorage.setItem(VIEW_STORAGE_KEY, view);
    let nextPath = viewPaths[view];
    if (view === 'directory') {
      nextPath = profileTarget?.domain
        ? `/directory/${encodeURIComponent(profileTarget.domain)}`
        : '/directory';
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
      const nextView = viewFromPath(window.location.pathname) ?? 'search';
      setProfileTarget(profileTargetFromPath(window.location.pathname, window.location.search));
      applyingPopState.current = true;
      setView(nextView);
    }
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  useEffect(() => {
    if (view === 'admin' && !currentUser?.is_admin) {
      setView('search');
    }
  }, [currentUser?.is_admin, view]);

  useEffect(() => {
    setProfileUsername(currentUser?.username ?? null);
  }, [currentUser?.username]);

  useEffect(() => {
    document.documentElement.classList.toggle('dark', themeMode === 'dark');
    window.localStorage.setItem(THEME_STORAGE_KEY, themeMode);
    window.dispatchEvent(new CustomEvent('iris-theme-change', { detail: themeMode }));
  }, [themeMode]);

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

  const navItems: Array<{ view: View; label: string; icon: ReactNode; adminOnly?: boolean }> = [
    { view: 'search', label: 'Search', icon: <Search size={15} /> },
    { view: 'bookshelf', label: 'Bookshelf', icon: <BookOpen size={15} /> },
    { view: 'people', label: 'People', icon: <Users size={15} /> },
    { view: 'directory', label: 'Directory', icon: <Orbit size={15} /> },
    { view: 'admin', label: 'Admin', icon: <LayoutDashboard size={15} />, adminOnly: true },
  ];
  const visibleNavItems = navItems.filter((item) => !item.adminOnly || currentUser?.is_admin);

  return (
    <AppShell>
      <Sidebar>
        <div className="flex h-14 shrink-0 items-center px-4 text-lg font-semibold tracking-tight md:h-16">
          iris
        </div>
        <nav className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto px-2 pb-2 md:block md:space-y-1 md:overflow-visible">
          {visibleNavItems.map((item) => (
            <Button
              key={item.view}
              type="button"
              onClick={() => {
                setDocumentUuid(null);
                if (item.view === 'directory') {
                  openDirectoryRoot();
                } else {
                  setView(item.view);
                }
              }}
              uiVariant="nav"
              className="w-auto md:w-full"
              data-active={view === item.view ? 'true' : undefined}
            >
              {item.icon}
              {item.label}
            </Button>
          ))}
        </nav>
        {currentUser && (
          <div className="hidden border-t p-2 md:block">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button uiVariant="nav" className="h-auto w-full justify-start py-2">
                  <Settings size={17} />
                  <span className="min-w-0 flex-1 truncate text-left">
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
      </Sidebar>
      <Workspace view={view}>
        {view === 'search' && <SearchView selectedDocumentUuid={documentUuid} onOpenDocument={openSearchDocument} />}
        {view === 'bookshelf' && <BookshelfView onDiscover={() => {
          setDocumentUuid(null);
          setView('search');
        }} />}
        {view === 'people' && <PeopleView />}
        {view === 'profile' && <ProfileView onUsernameChange={setProfileUsername} />}
        {view === 'directory' && (
          <DirectoryHub
            target={profileTarget}
            onOpenProfile={openProfile}
            onDirectoryRoot={openDirectoryRoot}
          />
        )}
        {view === 'admin' && currentUser?.is_admin && <AdminView />}
      </Workspace>
      {documentUuid !== null && <DocumentRouteDrawer documentUuid={documentUuid} reason={documentReason} onClose={closeDocumentDrawer} />}
    </AppShell>
  );
}

function readDocumentReason(state: unknown): string | null {
  if (!state || typeof state !== 'object' || !('documentReason' in state)) return null;
  const reason = (state as { documentReason?: unknown }).documentReason;
  return typeof reason === 'string' && reason.trim() ? reason : null;
}

export default function App() {
  return (
    <AuthGate>
      {(currentUser, onSignOut) => <IrisApp currentUser={currentUser} onSignOut={onSignOut} />}
    </AuthGate>
  );
}
