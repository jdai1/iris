export type View = 'search' | 'bookshelf' | 'directory' | 'explore' | 'graph' | 'admin';
export type ProfileTarget = { sourceId: number; domain: string } | null;

export const VIEW_STORAGE_KEY = 'iris.activeView';
export const views: View[] = ['search', 'bookshelf', 'directory', 'explore', 'graph', 'admin'];
export const viewPaths: Record<View, string> = {
  search: '/search',
  bookshelf: '/bookshelf',
  directory: '/directory',
  explore: '/explore',
  graph: '/graph',
  admin: '/admin',
};

export function documentUuidFromPath(pathname: string): string | null {
  const match = pathname.replace(/\/+$/, '').match(/^\/documents\/([^/]+)$/);
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

export function navigateTo(path: string, { replace = false }: { replace?: boolean } = {}) {
  if (typeof window === 'undefined') return;
  const current = `${window.location.pathname}${window.location.search}`;
  if (current === path) return;
  window.history[replace ? 'replaceState' : 'pushState'](null, '', path);
  window.dispatchEvent(new PopStateEvent('popstate'));
}

export function documentPath(documentUuid: string) {
  return `/documents/${encodeURIComponent(documentUuid)}`;
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
  if (normalized.startsWith('/directory/')) return 'directory';
  const match = views.find((view) => viewPaths[view] === normalized);
  return match ?? null;
}

export function profileTargetFromPath(pathname: string): ProfileTarget {
  const normalized = pathname.replace(/\/+$/, '');
  if (!normalized.startsWith('/directory/')) return null;
  const domain = decodeURIComponent(normalized.slice('/directory/'.length)).trim();
  return domain ? { sourceId: 0, domain } : null;
}

export function defaultArtifactWidth() {
  if (typeof window === 'undefined') return 560;
  const available = window.innerWidth - 208 - 24 - 32;
  return Math.min(900, Math.max(360, Math.round(available / 2)));
}
