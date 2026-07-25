import { ReactNode, useEffect, useRef, useState } from 'react';
import {
  Box,
  Stack,
} from '@chakra-ui/react';
import { BookOpen, LayoutDashboard, LogOut, Moon, Orbit, Search, Settings, Sun, UserCircle, Users } from 'lucide-react';
import { AuthGate } from './auth';
import { AdminView } from './views/AdminView';
import { BookshelfView } from './views/BookshelfView';
import { DirectoryHub } from './views/DirectoryHub';
import { PeopleView } from './views/PeopleView';
import { SearchView } from './views/SearchView';
import { directoryModeFromLocation, documentParentPath, documentPath, documentUuidFromPath, initialView, navigateTo, profileTargetFromPath, VIEW_STORAGE_KEY, viewFromPath, viewPaths, type DirectoryMode, type ProfileTarget, type View } from './app/navigation';
import { DocumentRouteDrawer } from './components/DocumentRouteDrawer';
import { AppShell, Sidebar, Workspace } from './layout';
import { Button } from './components/ui';
import type { User as IrisUser } from './types';

const THEME_STORAGE_KEY = 'iris.theme';
type ThemeMode = 'light' | 'dark';

function initialTheme(): ThemeMode {
  if (typeof document === 'undefined') return 'light';
  return document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light';
}

function IrisApp({ currentUser, onSignOut }: { currentUser: IrisUser | null; onSignOut: () => void }) {
  const [view, setView] = useState<View>(initialView);
  const [directoryMode, setDirectoryMode] = useState<DirectoryMode>(() =>
    typeof window === 'undefined'
      ? 'sources'
      : directoryModeFromLocation(window.location.pathname, window.location.search),
  );
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
  const [themeMode, setThemeMode] = useState<ThemeMode>(initialTheme);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const settingsRef = useRef<HTMLDivElement | null>(null);
  const applyingPopState = useRef(false);

  useEffect(() => {
    if (documentUuid !== null) return;
    window.localStorage.setItem(VIEW_STORAGE_KEY, view);
    let nextPath = viewPaths[view];
    if (view === 'directory') {
      if (directoryMode === 'sources') {
        nextPath = profileTarget?.domain
          ? `/directory/${encodeURIComponent(profileTarget.domain)}`
          : '/directory';
      } else {
        const params = new URLSearchParams({ mode: directoryMode });
        const focusedDocument = new URLSearchParams(window.location.search).get('document');
        if (focusedDocument) params.set('document', focusedDocument);
        if (profileTarget?.domain) params.set('domain', profileTarget.domain);
        nextPath = `/directory?${params.toString()}`;
      }
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
  }, [directoryMode, view, profileTarget?.domain]);

  useEffect(() => {
    function handlePopState() {
      const nextDocumentUuid = documentUuidFromPath(window.location.pathname);
      setDocumentUuid(nextDocumentUuid);
      setDocumentReason(nextDocumentUuid === null ? null : readDocumentReason(window.history.state));
      const nextView = viewFromPath(window.location.pathname) ?? 'search';
      setDirectoryMode(directoryModeFromLocation(window.location.pathname, window.location.search));
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
    document.documentElement.dataset.theme = themeMode;
    window.localStorage.setItem(THEME_STORAGE_KEY, themeMode);
    window.dispatchEvent(new CustomEvent('iris-theme-change', { detail: themeMode }));
  }, [themeMode]);

  useEffect(() => {
    if (!settingsOpen) return;
    function closeSettingsOnOutsideClick(event: PointerEvent) {
      const target = event.target;
      if (target instanceof Node && settingsRef.current?.contains(target)) return;
      setSettingsOpen(false);
    }
    document.addEventListener('pointerdown', closeSettingsOnOutsideClick);
    return () => document.removeEventListener('pointerdown', closeSettingsOnOutsideClick);
  }, [settingsOpen]);

  function openProfile(sourceId: number, domain: string) {
    setDocumentUuid(null);
    setDirectoryMode('sources');
    setProfileTarget({ sourceId, domain });
    setView('directory');
  }

  function openDirectoryRoot() {
    setDocumentUuid(null);
    setDirectoryMode('sources');
    setProfileTarget(null);
    setView('directory');
  }

  function openDirectoryMode(mode: DirectoryMode) {
    setDocumentUuid(null);
    setDirectoryMode(mode);
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
        <Box className="sidebar-brand">
          <span>iris</span>
        </Box>
        <Stack as="nav" className="sidebar-nav" gap="1">
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
              justifyContent="flex-start"
              data-active={view === item.view ? 'true' : undefined}
              bg="transparent"
              color={view === item.view ? 'iris.900' : 'iris.500'}
              fontSize="14px"
              fontWeight={view === item.view ? '600' : '500'}
              lineHeight="1"
              _hover={{
                bg: 'transparent',
                color: 'iris.900',
              }}
            >
              {item.icon}
              {item.label}
            </Button>
          ))}
        </Stack>
        {currentUser && (
          <div className="sidebar-settings" ref={settingsRef}>
            {settingsOpen && (
              <div className="settings-menu">
                <div className="settings-menu-row settings-menu-muted">
                  <UserCircle size={16} />
                  <span>{currentUser.email || currentUser.display_name}</span>
                </div>
                <div className="settings-menu-divider" />
                <button
                  className="settings-menu-row"
                  type="button"
                  onClick={() => setThemeMode((mode) => (mode === 'dark' ? 'light' : 'dark'))}
                >
                  {themeMode === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
                  <span>{themeMode === 'dark' ? 'Light mode' : 'Dark mode'}</span>
                </button>
                <div className="settings-menu-divider" />
                <button className="settings-menu-row" type="button" onClick={onSignOut}>
                  <LogOut size={16} />
                  <span>Log out</span>
                </button>
              </div>
            )}
            <button
              className="sidebar-settings-toggle"
              type="button"
              onClick={() => setSettingsOpen((value) => !value)}
              aria-expanded={settingsOpen}
            >
              <Settings size={17} />
              <span>Settings</span>
            </button>
            <div className="sidebar-settings-meta">
              {currentUser.display_name || currentUser.email}
            </div>
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
        {view === 'directory' && (
          <DirectoryHub
            mode={directoryMode}
            target={profileTarget}
            onModeChange={openDirectoryMode}
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
