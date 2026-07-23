export type View = 'search' | 'bookshelf' | 'people' | 'directory' | 'admin';
export type DirectoryMode = 'sources' | 'explore' | 'graph';
export type ProfileTarget = { sourceId: number; domain: string } | null;

export const VIEW_STORAGE_KEY = 'iris.activeView';
export const views: View[] = ['search', 'bookshelf', 'people', 'directory', 'admin'];
export const viewPaths: Record<View, string> = {
  search: '/search',
  bookshelf: '/bookshelf',
  people: '/people',
  directory: '/directory',
  admin: '/admin',
};

export function documentUuidFromPath(pathname: string): string | null {
  const match = pathname.replace(/\/+$/, '').match(/\/documents\/([^/]+)$/);
  if (!match) return null;
  try {
    return decodeURIComponent(match[1]);
  } catch {
    return null;
  }
}

export function collectionIdFromSearch(search: string): number | null {
  const value = new URLSearchParams(search).get('collection');
  if (!value) return null;
  const collectionId = Number(value);
  return Number.isSafeInteger(collectionId) && collectionId > 0 ? collectionId : null;
}

export function navigateTo(path: string, { replace = false, state = null }: { replace?: boolean; state?: unknown } = {}) {
  if (typeof window === 'undefined') return;
  const current = `${window.location.pathname}${window.location.search}`;
  if (current === path) return;
  window.history[replace ? 'replaceState' : 'pushState'](state, '', path);
  window.dispatchEvent(new PopStateEvent('popstate'));
}

export function documentPath(documentUuid: string) {
  const pathname = typeof window === 'undefined' ? '/search' : window.location.pathname;
  const search = typeof window === 'undefined' ? '' : window.location.search;
  const parentPath = documentParentPath(pathname);
  return `${parentPath}/documents/${encodeURIComponent(documentUuid)}${search}`;
}

export function documentParentPath(pathname: string): string {
  const normalized = pathname.replace(/\/+$/, '') || '/search';
  const withoutDocument = normalized.replace(/\/documents\/[^/]+$/, '');
  if (viewFromPath(withoutDocument)) return withoutDocument;
  return '/search';
}

export function initialView(): View {
  if (typeof window === 'undefined') return 'search';
  const pathView = viewFromPath(window.location.pathname);
  if (pathView) return pathView;
  const saved = window.localStorage.getItem(VIEW_STORAGE_KEY);
  return views.includes(saved as View) ? (saved as View) : 'search';
}

export function viewFromPath(pathname: string): View | null {
  const normalized = pathname.replace(/\/+$/, '') || '/';
  if (normalized === '/') return null;
  if (normalized === '/explore' || normalized.startsWith('/explore/')) return 'directory';
  if (normalized === '/graph' || normalized.startsWith('/graph/')) return 'directory';
  const match = views.find((view) => normalized === viewPaths[view] || normalized.startsWith(`${viewPaths[view]}/`));
  return match ?? null;
}

export function directoryModeFromLocation(pathname: string, search: string): DirectoryMode {
  const normalized = pathname.replace(/\/+$/, '') || '/';
  if (normalized === '/explore' || normalized.startsWith('/explore/')) return 'explore';
  if (normalized === '/graph' || normalized.startsWith('/graph/')) return 'graph';
  const mode = new URLSearchParams(search).get('mode');
  return mode === 'explore' || mode === 'graph' ? mode : 'sources';
}

export function profileTargetFromPath(pathname: string, search = ''): ProfileTarget {
  const normalized = pathname.replace(/\/+$/, '');
  const supportsDomainQuery = normalized === '/directory'
    || normalized === '/graph'
    || normalized.startsWith('/graph/')
    || normalized === '/explore'
    || normalized.startsWith('/explore/');
  const domain = normalized.startsWith('/directory/')
    ? decodeURIComponent(normalized.slice('/directory/'.length).split('/documents/')[0]).trim()
    : supportsDomainQuery
      ? new URLSearchParams(search).get('domain')?.trim()
      : null;
  return domain ? { sourceId: 0, domain } : null;
}

export function defaultArtifactWidth() {
  if (typeof window === 'undefined') return 560;
  const available = window.innerWidth - 208 - 24 - 32;
  return Math.min(900, Math.max(360, Math.round(available / 2)));
}
