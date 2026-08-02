import { ReactNode, useEffect, useMemo, useRef, useState } from 'react';
import { ArrowLeft, ArrowUpRight, ChevronDown, ChevronUp, FileText, Folder, GitFork, LayoutPanelLeft, LayoutTemplate, PanelLeftClose } from 'lucide-react';
import { getBookshelfCollections, getDirectorySources, getDocuments, getGraph, getSourceProfileAnalysis, searchGraphSources } from '../api';
import { GraphExplorer } from '../GraphExplorer';
import { emptyPage } from '../app/paging';
import { documentPath, navigateTo, type ProfileTarget } from '../app/navigation';
import { DenseDocumentTable } from '../components/DenseDocumentTable';
import { DenseTableViewport, denseTableHeaderClass, denseTableRowClass } from '../components/ui/dense-table';
import { FilterBar } from '../components/FilterBar';
import { OverflowText } from '../components/OverflowText';
import { ProfilePagination, type PageState } from '../components/Pagination';
import { ProfileAnalysisCard } from '../components/ProfileAnalysisCard';
import { Button, SearchInput, StateMessage } from '../components/ui';
import { cn } from '../lib/utils';
import type { AdminSource, BookshelfCollection, BookshelfEntry, DirectorySource, DirectorySourceSort, Document, GraphEdge, GraphNode, GraphResponse, Page, SortDirection, SourceProfileAnalysis } from '../types';

type SourceProfileTab = 'profile' | 'essays' | 'collections' | 'graph';
type DirectoryFilterKind = 'text' | 'tag';
type DirectoryFilter = { id: string; kind: DirectoryFilterKind; value: string };
const directoryHeaderSortButtonClass = 'h-auto justify-end p-0 text-xs font-semibold uppercase hover:bg-transparent';

function defaultDirectorySortDirection(sort: DirectorySourceSort): SortDirection {
  return sort === 'source' ? 'asc' : 'desc';
}

function directorySortLabel(label: string, sort: DirectorySourceSort, activeSort: DirectorySourceSort, direction: SortDirection): string {
  if (sort !== activeSort) return label;
  return `${label} ${direction === 'asc' ? '↑' : '↓'}`;
}

function formatCompactCount(value: number) {
  return new Intl.NumberFormat(undefined, { notation: 'compact', maximumFractionDigits: 1 }).format(value);
}

function formatDirectoryDate(value: string | null) {
  if (!value) return '-';
  return new Date(value).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

function filterValues(filters: DirectoryFilter[], kind: DirectoryFilterKind) {
  return filters.filter((filter) => filter.kind === kind).map((filter) => filter.value);
}

export function DirectoryView({
  target,
  onOpenProfile,
  onDirectoryRoot,
}: {
  target: ProfileTarget;
  onOpenProfile: (sourceId: number, domain: string) => void;
  onDirectoryRoot: () => void;
}) {
  const [directoryFilters, setDirectoryFilters] = useState<DirectoryFilter[]>([]);
  const [documentFilters, setDocumentFilters] = useState<DirectoryFilter[]>([]);
  const [explorerCollapsed, setExplorerCollapsed] = useState(false);
  const [selectedSource, setSelectedSource] = useState<AdminSource | null>(null);
  const [directoryPage, setDirectoryPage] = useState<Page<DirectorySource>>(emptyPage);
  const [explorerContextLoading, setExplorerContextLoading] = useState(false);
  const [directorySort, setDirectorySort] = useState<DirectorySourceSort>('essays');
  const [directorySortDirection, setDirectorySortDirection] = useState<SortDirection>('desc');
  const [documentsPage, setDocumentsPage] = useState<Page<Document>>(emptyPage);
  const [profileAnalysis, setProfileAnalysis] = useState<SourceProfileAnalysis | null>(null);
  const [profileCollections, setProfileCollections] = useState<BookshelfCollection[]>([]);
  const [profileGraph, setProfileGraph] = useState<GraphResponse | null>(null);
  const [activeProfileTab, setActiveProfileTab] = useState<SourceProfileTab>('profile');
  const [documentPageState, setDocumentPageState] = useState<PageState>({ limit: 50, offset: 0 });
  const [directoryPageState, setDirectoryPageState] = useState<PageState>({ limit: 50, offset: 0 });
  const [loading, setLoading] = useState(true);
  const [profileLoading, setProfileLoading] = useState(Boolean(target));
  const [documentsRefreshing, setDocumentsRefreshing] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const didLoadDirectoryRef = useRef(false);
  const sourceLoadKeyRef = useRef<string | null>(null);
  const preserveDirectoryContextRef = useRef(false);
  const refreshRequestIdRef = useRef(0);
  const documentsRequestIdRef = useRef(0);
  const profileCollectionGroups = useMemo(
    () => target ? sourceCollectionGroups(profileCollections, target.sourceId, target.domain) : [],
    [profileCollections, target?.sourceId, target?.domain],
  );
  const activeSelectedSource = selectedSource?.canonical_domain === target?.domain ? selectedSource : null;
  const activeDirectorySource = target
    ? directoryPage.items.find((source) => source.canonical_domain === target.domain) ?? null
    : null;
  const profileCollectionCount = activeDirectorySource?.collection_count ?? (profileLoading ? null : profileCollectionGroups.length);
  const showProfileCollections = profileCollectionCount === null || profileCollectionCount > 0;
  const resolvedSourceId = activeSelectedSource?.id ?? target?.sourceId ?? 0;
  const profileNetwork = useMemo(
    () => target && profileGraph ? sourceNetwork(profileGraph, `source:${resolvedSourceId}`) : { inbound: [], outbound: [] },
    [profileGraph, resolvedSourceId, target?.domain],
  );

  useEffect(() => {
    setActiveProfileTab('profile');
    if (target) {
      setProfileLoading(true);
    }
  }, [target?.sourceId, target?.domain]);

  useEffect(() => {
    if (!target || directoryPage.items.length > 0) return;
    let cancelled = false;
    setExplorerContextLoading(true);
    getDirectorySources({
      status: 'indexed',
      textFilters: filterValues(directoryFilters, 'text'),
      tags: filterValues(directoryFilters, 'tag'),
      sort: directorySort,
      direction: directorySortDirection,
      ...directoryPageState,
    })
      .then((page) => {
        if (!cancelled) setDirectoryPage(page);
      })
      .catch(() => {
        // A directly opened profile can remain usable without table context.
      })
      .finally(() => {
        if (!cancelled) setExplorerContextLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [target?.sourceId, target?.domain]);

  async function refresh(
    nextQuery = target?.domain ?? '',
    nextSelected = target,
    nextPage = documentPageState,
    nextDirectoryPage = directoryPageState,
    nextSort = directorySort,
    nextSortDirection = directorySortDirection,
    nextDirectoryFilters = directoryFilters,
    nextDocumentFilters = documentFilters,
  ) {
    const requestId = ++refreshRequestIdRef.current;
    documentsRequestIdRef.current += 1;
    setDocumentsRefreshing(false);
    const firstLoad = !didLoadDirectoryRef.current;
    setLoading(firstLoad && !nextSelected);
    setProfileLoading(Boolean(nextSelected));
    setRefreshing(!firstLoad);
    setError(null);
    try {
      const normalizedQuery = nextQuery.trim();
      if (!nextSelected) {
        const tablePage = await getDirectorySources({
          status: 'indexed',
          textFilters: filterValues(nextDirectoryFilters, 'text'),
          tags: filterValues(nextDirectoryFilters, 'tag'),
          sort: nextSort,
          direction: nextSortDirection,
          ...nextDirectoryPage,
        });
        if (requestId !== refreshRequestIdRef.current) return;
        setDirectoryPage(tablePage);
        setSelectedSource(null);
        setDocumentsPage(emptyPage<Document>());
        setProfileAnalysis(null);
        setProfileCollections([]);
        setProfileGraph(null);
        setProfileLoading(false);
        return;
      }
      const sources = await searchGraphSources(normalizedQuery, 25);
      if (requestId !== refreshRequestIdRef.current) return;
      const source =
        (nextSelected?.sourceId ? sources.find((item) => item.id === nextSelected.sourceId) : null) ??
        sources.find((item) => item.canonical_domain === normalizedQuery.toLowerCase()) ??
        (normalizedQuery ? sources[0] : null) ??
        null;
      const nextProfile = source ? { sourceId: source.id, domain: source.canonical_domain } : null;
      setSelectedSource(source);
      const [documents, analysis, collections, graph] = nextProfile
        ? await Promise.all([
            getDocuments({
              ...nextPage,
              sourceId: nextProfile.sourceId,
              documentType: 'essay',
              textFilters: filterValues(nextDocumentFilters, 'text'),
              tags: filterValues(nextDocumentFilters, 'tag'),
            }),
            getSourceProfileAnalysis(nextProfile.sourceId).catch(() => null),
            getBookshelfCollections().catch(() => []),
            getGraph({ mode: 'sources', sourceId: nextProfile.sourceId, limit: 80, depth: 1 }).catch(() => null),
          ])
        : [emptyPage<Document>(), null, [], null];
      if (requestId !== refreshRequestIdRef.current) return;
      setDocumentsPage(documents);
      setProfileAnalysis(analysis);
      setProfileCollections(collections);
      setProfileGraph(graph);
    } catch (err) {
      if (requestId === refreshRequestIdRef.current) {
        setError(err instanceof Error ? err.message : 'Directory failed');
      }
    } finally {
      if (requestId !== refreshRequestIdRef.current) return;
      didLoadDirectoryRef.current = true;
      setLoading(false);
      setProfileLoading(false);
      setRefreshing(false);
    }
  }

  async function refreshProfileDocuments(nextPage: PageState, nextFilters = documentFilters) {
    if (!resolvedSourceId) return;
    const requestId = ++documentsRequestIdRef.current;
    setDocumentsRefreshing(true);
    setError(null);
    try {
      const documents = await getDocuments({
        ...nextPage,
        sourceId: resolvedSourceId,
        documentType: 'essay',
        textFilters: filterValues(nextFilters, 'text'),
        tags: filterValues(nextFilters, 'tag'),
      });
      if (requestId !== documentsRequestIdRef.current) return;
      setDocumentsPage(documents);
    } catch (err) {
      if (requestId === documentsRequestIdRef.current) {
        setError(err instanceof Error ? err.message : 'Could not filter documents');
      }
    } finally {
      if (requestId === documentsRequestIdRef.current) setDocumentsRefreshing(false);
    }
  }

  useEffect(() => {
    if (!target) {
      sourceLoadKeyRef.current = null;
      return;
    }
    const loadKey = `${target.sourceId}:${target.domain}`;
    if (sourceLoadKeyRef.current === loadKey) return;
    sourceLoadKeyRef.current = loadKey;
    const nextPage = { limit: 50, offset: 0 };
    setDocumentPageState(nextPage);
    setDocumentFilters([]);
    refresh(target.domain, target, nextPage, directoryPageState, directorySort, directorySortDirection, directoryFilters, []);
  }, [target?.sourceId, target?.domain]);

  useEffect(() => {
    if (target) return;
    if (preserveDirectoryContextRef.current) {
      preserveDirectoryContextRef.current = false;
      return;
    }
    const timeout = window.setTimeout(() => {
      const nextDirectoryPage = { limit: directoryPageState.limit, offset: 0 };
      setDirectoryPageState(nextDirectoryPage);
      refresh('', null, documentPageState, nextDirectoryPage, directorySort, directorySortDirection, directoryFilters);
    }, 160);
    return () => window.clearTimeout(timeout);
  }, [directoryFilters, target?.domain]);

  function updateDocumentFilters(nextFilters: DirectoryFilter[]) {
    const nextPage = { limit: documentPageState.limit, offset: 0 };
    setDocumentFilters(nextFilters);
    setDocumentPageState(nextPage);
    refreshProfileDocuments(nextPage, nextFilters);
  }

  function openSourceProfile(source: Pick<AdminSource, 'id' | 'canonical_domain'>) {
    setSelectedSource(null);
    setDocumentsPage(emptyPage<Document>());
    setProfileAnalysis(null);
    setProfileCollections([]);
    setProfileGraph(null);
    setProfileLoading(true);
    setActiveProfileTab('profile');
    onOpenProfile(source.id, source.canonical_domain);
  }

  function pageProfileDocuments(nextPage: PageState) {
    setDocumentPageState(nextPage);
    refreshProfileDocuments(nextPage);
  }

  function updateDirectorySort(nextSort: DirectorySourceSort) {
    const nextPage = { limit: directoryPageState.limit, offset: 0 };
    const nextDirection: SortDirection = nextSort === directorySort ? (directorySortDirection === 'desc' ? 'asc' : 'desc') : defaultDirectorySortDirection(nextSort);
    setDirectorySort(nextSort);
    setDirectorySortDirection(nextDirection);
    setDirectoryPageState(nextPage);
    refresh('', target, documentPageState, nextPage, nextSort, nextDirection);
  }

  function pageDirectory(nextPage: PageState) {
    setDirectoryPageState(nextPage);
    refresh('', target, documentPageState, nextPage);
  }

  function selectDirectorySource(source: DirectorySource) {
    openSourceProfile({
      id: source.id,
      canonical_domain: source.canonical_domain,
    });
  }

  function showDirectoryRoot() {
    preserveDirectoryContextRef.current = true;
    setSelectedSource(null);
    setProfileAnalysis(null);
    setProfileCollections([]);
    setProfileGraph(null);
    setActiveProfileTab('profile');
    setDocumentsPage(emptyPage<Document>());
    onDirectoryRoot();
    if (directoryPage.items.length === 0) {
      refresh('', null, documentPageState, directoryPageState);
    }
  }

  function openDirectoryDrawer(document: Document) {
    navigateTo(documentPath(document.uuid));
  }

  return (
    <section className={cn(
      'min-h-svh min-w-0',
      target && `grid grid-cols-1 ${explorerCollapsed ? 'lg:grid-cols-[3rem_minmax(0,1fr)]' : 'lg:grid-cols-[13.75rem_minmax(0,1fr)]'}`,
    )}>
      {target && (
        <DirectorySourceExplorer
          page={directoryPage}
          loading={explorerContextLoading}
          collapsed={explorerCollapsed}
          selectedDomain={target.domain}
          onShowAll={showDirectoryRoot}
          onSelect={selectDirectorySource}
          onToggleCollapsed={() => setExplorerCollapsed((collapsed) => !collapsed)}
        />
      )}
      <div className={cn('min-w-0', !target && 'p-4 sm:p-6')}>
      {!target && (
        <FilterBar
          className="mb-5"
          context="sources"
          filters={directoryFilters}
          onChange={setDirectoryFilters}
        />
      )}

      {error && <StateMessage className="mb-5" tone="error">{error}</StateMessage>}
      {loading && !target && <TableSkeleton rows={10} />}

      {!loading && !target && (
        <DenseTableViewport>
          <div className={`min-w-[880px] transition-opacity ${refreshing ? 'opacity-60' : 'opacity-100'}`} role="table" aria-label="Sources">
            <div className={`${denseTableHeaderClass} grid-cols-[minmax(8rem,0.8fr)_minmax(16rem,2fr)_repeat(4,5.5rem)_7rem]`} role="row">
              <Button className={cn(directoryHeaderSortButtonClass, 'justify-start')} uiVariant="rowAction" type="button" onClick={() => updateDirectorySort('source')}>{directorySortLabel('Source', 'source', directorySort, directorySortDirection)}</Button>
              <span>About</span>
              <Button className={directoryHeaderSortButtonClass} uiVariant="rowAction" type="button" onClick={() => updateDirectorySort('essays')}>{directorySortLabel('Essays', 'essays', directorySort, directorySortDirection)}</Button>
              <Button className={directoryHeaderSortButtonClass} uiVariant="rowAction" type="button" onClick={() => updateDirectorySort('essay_references')} data-tooltip="Distinct indexed essays referenced by this source">{directorySortLabel('Essay refs', 'essay_references', directorySort, directorySortDirection)}</Button>
              <Button className={directoryHeaderSortButtonClass} uiVariant="rowAction" type="button" onClick={() => updateDirectorySort('external_sources')} data-tooltip="Distinct external indexed sources referenced by this source">{directorySortLabel('Sources', 'external_sources', directorySort, directorySortDirection)}</Button>
              <Button className={directoryHeaderSortButtonClass} uiVariant="rowAction" type="button" onClick={() => updateDirectorySort('documents')}>{directorySortLabel('Docs', 'documents', directorySort, directorySortDirection)}</Button>
              <Button className={directoryHeaderSortButtonClass} uiVariant="rowAction" type="button" onClick={() => updateDirectorySort('recent')}>{directorySortLabel('Updated', 'recent', directorySort, directorySortDirection)}</Button>
            </div>
            {directoryPage.items.map((source) => (
              <div key={source.id} className={`${denseTableRowClass} cursor-pointer grid-cols-[minmax(8rem,0.8fr)_minmax(16rem,2fr)_repeat(4,5.5rem)_7rem] hover:bg-muted/50`} role="row" tabIndex={0} onClick={() => selectDirectorySource(source)} onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') selectDirectorySource(source);
              }}>
                <span className="flex min-w-0 items-center gap-1.5" data-label="Source">
                  <strong className="truncate font-medium">{source.canonical_domain}</strong>
                  <a className="shrink-0 text-muted-foreground hover:text-foreground" href={source.url} target="_blank" rel="noreferrer" aria-label="Open source" onClick={(event) => event.stopPropagation()}>
                    <ArrowUpRight size={15} />
                  </a>
                </span>
                <span className="min-w-0 truncate text-muted-foreground" data-label="About">
                  <OverflowText>{source.description || source.name || '-'}</OverflowText>
                </span>
                <span className="text-right tabular-nums text-muted-foreground" data-label="Essays">
                  <strong>{formatCompactCount(source.essay_count)}</strong>
                </span>
                <span className="text-right tabular-nums text-muted-foreground" data-label="Essay refs">
                  <strong>{formatCompactCount(source.essay_reference_count)}</strong>
                </span>
                <span className="text-right tabular-nums text-muted-foreground" data-label="Sources">
                  <strong>{formatCompactCount(source.external_source_count)}</strong>
                </span>
                <span className="text-right tabular-nums text-muted-foreground" data-label="Docs">
                  <strong>{formatCompactCount(source.document_count)}</strong>
                </span>
                <span className="text-right text-xs text-muted-foreground" data-label="Updated">
                  <strong>{formatDirectoryDate(source.last_checked_at)}</strong>
                </span>
              </div>
            ))}
            {directoryPage.items.length === 0 && (
              <div className="border-b px-4 py-12 text-center text-sm text-muted-foreground">
                No sources match these filters.
              </div>
            )}
          </div>
          <ProfilePagination page={directoryPage} onChange={pageDirectory} />
        </DenseTableViewport>
      )}

      {target && (
        <div className="min-h-[calc(100svh-5rem)]" aria-busy={profileLoading}>
          <div className="flex h-16 items-center border-b px-5">
            <Button className="mr-3 -ml-2 h-8 gap-1.5 px-2 text-muted-foreground lg:hidden" uiVariant="ghost" size="sm" type="button" onClick={showDirectoryRoot}>
              <ArrowLeft size={14} />
              Sources
            </Button>
            <div className="h-5 border-l lg:hidden" />
            <div className="ml-4 min-w-0 lg:ml-0">
              <h3 className="flex items-center gap-2 text-lg font-semibold">
                <span className="truncate">{activeSelectedSource?.canonical_domain || target.domain}</span>
                <a className="text-muted-foreground hover:text-foreground" href={activeSelectedSource?.url ?? `https://${target.domain}`} target="_blank" rel="noreferrer" aria-label="Open source">
                  <ArrowUpRight size={16} />
                </a>
              </h3>
            </div>
          </div>
          <nav className="flex min-h-12 items-center gap-4 overflow-x-auto border-b px-5" aria-label="Source views">
            <SourceViewButton
              active={activeProfileTab === 'profile'}
              icon={<LayoutTemplate size={14} />}
              label="Overview"
              onClick={() => setActiveProfileTab('profile')}
            />
            <SourceViewButton
              active={activeProfileTab === 'essays'}
              icon={<FileText size={14} />}
              label="Essays"
              count={activeDirectorySource?.essay_count ?? (profileLoading ? null : documentsPage.total)}
              onClick={() => setActiveProfileTab('essays')}
            />
            {showProfileCollections && (
              <SourceViewButton
                active={activeProfileTab === 'collections'}
                icon={<Folder size={14} />}
                label="Collections"
                count={profileCollectionCount}
                onClick={() => setActiveProfileTab('collections')}
              />
            )}
            <SourceViewButton
              active={activeProfileTab === 'graph'}
              icon={<GitFork size={14} />}
              label="Graph"
              onClick={() => setActiveProfileTab('graph')}
            />
          </nav>
          <div className="min-h-[calc(100svh-12rem)] p-5">
            {profileLoading && <SourceProfileSkeleton />}
            {!profileLoading && activeProfileTab === 'profile' && (
              <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,2fr)_minmax(18rem,1fr)]">
                <ProfileAnalysisCard analysis={profileAnalysis} />
                <SourceNetworkPanel inbound={profileNetwork.inbound} outbound={profileNetwork.outbound} onOpenProfile={onOpenProfile} />
              </div>
            )}
            {!profileLoading && activeProfileTab === 'essays' && (
              <>
                <FilterBar
                  className="mb-4"
                  context="documents"
                  filters={documentFilters}
                  onChange={updateDocumentFilters}
                />
                <div className={`overflow-x-auto transition-opacity ${documentsRefreshing ? 'opacity-60' : 'opacity-100'}`} aria-busy={documentsRefreshing}>
                  <DirectoryDocumentTable documents={documentsPage.items} onOpenDocument={openDirectoryDrawer} />
                  {documentsPage.items.length === 0 && (
                    <div className="min-w-[760px] border-b px-4 py-12 text-center text-sm text-muted-foreground">
                      No documents match these filters.
                    </div>
                  )}
                </div>
                <ProfilePagination page={documentsPage} onChange={pageProfileDocuments} />
              </>
            )}
            {!profileLoading && activeProfileTab === 'collections' && (
              <SourceCollectionsTab groups={profileCollectionGroups} onOpenDocument={openDirectoryDrawer} />
            )}
            {!profileLoading && activeProfileTab === 'graph' && (
              <div className="h-[calc(100svh-9.5rem)] min-h-0 overflow-hidden rounded-xl border">
                <GraphExplorer
                  key={target.domain}
                  initialDomain={target.domain}
                />
              </div>
            )}
          </div>
        </div>
      )}
      </div>
    </section>
  );
}

function DirectorySourceExplorer({
  page,
  loading,
  collapsed,
  selectedDomain,
  onShowAll,
  onSelect,
  onToggleCollapsed,
}: {
  page: Page<DirectorySource>;
  loading: boolean;
  collapsed: boolean;
  selectedDomain: string | null;
  onShowAll: () => void;
  onSelect: (source: DirectorySource) => void;
  onToggleCollapsed: () => void;
}) {
  const [query, setQuery] = useState('');
  const normalizedQuery = query.trim().toLowerCase();
  const visibleSources = useMemo(
    () => normalizedQuery
      ? page.items.filter((source) => `${source.canonical_domain} ${source.name ?? ''} ${source.description ?? ''}`.toLowerCase().includes(normalizedQuery))
      : page.items,
    [normalizedQuery, page.items],
  );
  const selectedIndex = visibleSources.findIndex((source) => source.canonical_domain === selectedDomain);

  function moveSelection(direction: -1 | 1) {
    if (!visibleSources.length) return;
    const nextIndex = selectedIndex < 0
      ? direction === 1 ? 0 : visibleSources.length - 1
      : selectedIndex + direction;
    const nextSource = visibleSources[nextIndex];
    if (nextSource) onSelect(nextSource);
  }

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey || isEditableTarget(event.target)) return;
      const key = event.key.toLowerCase();
      if (key !== 'j' && key !== 'k') return;
      event.preventDefault();
      moveSelection(key === 'j' ? 1 : -1);
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [selectedDomain, visibleSources]);

  if (collapsed) {
    return (
      <aside className="sticky top-0 hidden h-svh self-start overflow-hidden border-r bg-muted/20 lg:flex lg:flex-col lg:items-center" aria-label="Collapsed source explorer">
        <Button className="mt-3 size-8" uiVariant="plainIcon" type="button" onClick={onToggleCollapsed} aria-label="Open source explorer" data-tooltip="Open source explorer">
          <LayoutPanelLeft size={15} />
        </Button>
        <Button className="mt-1 size-8" uiVariant="plainIcon" type="button" onClick={onShowAll} aria-label="Back to sources" data-tooltip="Back to sources">
          <ArrowLeft size={15} />
        </Button>
      </aside>
    );
  }

  return (
    <aside className="sticky top-0 hidden h-svh min-w-0 self-start overflow-hidden border-r bg-muted/20 lg:flex lg:flex-col" aria-label="Source explorer">
      <div className="flex h-14 shrink-0 items-center justify-between gap-2 px-4">
        <button className="flex h-8 min-w-0 items-center gap-1.5 rounded-md px-1.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground" type="button" onClick={onShowAll}>
          <ArrowLeft size={14} />
          <span>Sources</span>
        </button>
        <Button className="size-7" uiVariant="plainIcon" type="button" onClick={onToggleCollapsed} aria-label="Collapse source explorer" data-tooltip="Collapse explorer">
          <PanelLeftClose size={14} />
        </Button>
      </div>
      <div className="px-2 pb-2">
        <SearchInput
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search this page"
          aria-label="Search sources on this page"
          wrapperClassName="min-h-8 px-2"
          className="min-h-7 text-xs"
        />
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
        {loading && explorerSkeleton()}
        {!loading && page.items.length === 0 && (
          <p className="px-2 py-5 text-center text-xs text-muted-foreground">No table context.</p>
        )}
        {!loading && page.items.length > 0 && visibleSources.length === 0 && (
          <p className="px-2 py-5 text-center text-xs text-muted-foreground">No sources found.</p>
        )}
        {!loading && visibleSources.map((source) => (
          <button
            className={`flex h-8 w-full min-w-0 items-center rounded-md px-2 text-left text-xs ${selectedDomain === source.canonical_domain ? 'bg-accent text-accent-foreground' : 'text-muted-foreground hover:bg-accent/70 hover:text-accent-foreground'}`}
            type="button"
            key={source.id}
            title={source.canonical_domain}
            onClick={() => onSelect(source)}
          >
            <span className="min-w-0 truncate">{source.canonical_domain}</span>
          </button>
        ))}
      </div>
      <div className="grid shrink-0 grid-cols-2 gap-1 border-t p-2 text-xs">
        <button
          className="flex h-8 min-w-0 items-center justify-center gap-1 rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground disabled:pointer-events-none disabled:opacity-35"
          type="button"
          onClick={() => moveSelection(-1)}
          disabled={!visibleSources.length || selectedIndex === 0}
          aria-label="Previous source (K)"
        >
          <ChevronUp size={13} />
          <span>Previous</span>
          <kbd className="text-[10px] opacity-60">K</kbd>
        </button>
        <button
          className="flex h-8 min-w-0 items-center justify-center gap-1 rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground disabled:pointer-events-none disabled:opacity-35"
          type="button"
          onClick={() => moveSelection(1)}
          disabled={!visibleSources.length || selectedIndex === visibleSources.length - 1}
          aria-label="Next source (J)"
        >
          <span>Next</span>
          <kbd className="text-[10px] opacity-60">J</kbd>
          <ChevronDown size={13} />
        </button>
      </div>
    </aside>
  );
}

function isEditableTarget(target: EventTarget | null) {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable || Boolean(target.closest('input, textarea, select, [contenteditable="true"]'));
}

function explorerSkeleton() {
  return (
    <div className="grid gap-2 px-2 py-1" aria-label="Loading sources">
      {Array.from({ length: 8 }).map((_, index) => (
        <span className="h-6 animate-pulse rounded bg-muted" key={index} />
      ))}
    </div>
  );
}

function SourceViewButton({
  active,
  icon,
  label,
  count,
  onClick,
}: {
  active: boolean;
  icon: ReactNode;
  label: string;
  count?: number | null;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className={`inline-flex h-12 shrink-0 items-center gap-2 border-b-2 px-0 text-sm font-medium transition-colors ${
        active ? 'border-primary text-foreground' : 'border-transparent text-muted-foreground hover:text-foreground'
      }`}
      aria-pressed={active}
      onClick={onClick}
    >
      {icon}
      <span>{label}</span>
      {count !== undefined && (
        <small className={`rounded-full bg-muted px-1.5 py-0.5 text-[10px] tabular-nums ${typeof count === 'number' ? '' : 'invisible'}`} aria-hidden={typeof count !== 'number'}>
          {typeof count === 'number' ? count : '000'}
        </small>
      )}
    </button>
  );
}

function DirectoryDocumentTable({ documents, onOpenDocument }: { documents: Document[]; onOpenDocument: (document: Document) => void }) {
  return (
    <DenseDocumentTable
      rows={documents.map((document) => ({
        document,
        tags: document.topics,
        date: formatDirectoryDate(document.published_at),
      }))}
      ariaLabel="Source documents"
      showNote={false}
      showSource={false}
      onPrimaryClick={(row) => onOpenDocument(row.document)}
    />
  );
}

function sourceCollectionGroups(collections: BookshelfCollection[], sourceId: number, domain: string): Array<{ collection: BookshelfCollection; items: BookshelfEntry[] }> {
  return collections
    .map((collection) => ({
      collection,
      items: collection.items.filter((entry) => entry.document.source_id === sourceId || entry.document.source_domain === domain),
    }))
    .filter((group) => group.items.length > 0)
    .sort((a, b) => b.items.length - a.items.length || a.collection.name.localeCompare(b.collection.name));
}

function SourceCollectionsTab({
  groups,
  onOpenDocument,
}: {
  groups: Array<{ collection: BookshelfCollection; items: BookshelfEntry[] }>;
  onOpenDocument: (document: Document) => void;
}) {
  if (!groups.length) {
    return (
      <StateMessage>
        No collections include documents from this source.
      </StateMessage>
    );
  }

  return (
    <div className="space-y-5">
      {groups.map(({ collection, items }) => (
        <section key={collection.id}>
          <div className="flex items-center justify-between border-b py-3">
            <strong>{collection.name}</strong>
            <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">{items.length}</span>
          </div>
          <DenseDocumentTable
            rows={items.map((entry) => ({
              document: entry.document,
              tags: entry.tags.length ? entry.tags : entry.document.topics,
              date: formatDirectoryDate(entry.read_at ?? entry.first_seen_at ?? entry.favorited_at ?? entry.document.published_at),
            }))}
            ariaLabel={`${collection.name} documents from this source`}
            showNote={false}
            showSource={false}
            onPrimaryClick={(row) => onOpenDocument(row.document)}
          />
        </section>
      ))}
    </div>
  );
}

type SourceNetworkItem = {
  node: GraphNode;
  edge: GraphEdge;
};

function sourceNetwork(graph: GraphResponse, selectedId: string): { inbound: SourceNetworkItem[]; outbound: SourceNetworkItem[] } {
  const nodesById = new Map(graph.nodes.map((node) => [node.id, node]));
  return {
    inbound: rankedSourceNetworkItems(graph.edges, nodesById, selectedId, 'inbound'),
    outbound: rankedSourceNetworkItems(graph.edges, nodesById, selectedId, 'outbound'),
  };
}

function rankedSourceNetworkItems(
  edges: GraphEdge[],
  nodesById: Map<string, GraphNode>,
  selectedId: string,
  direction: 'inbound' | 'outbound',
): SourceNetworkItem[] {
  return edges
    .filter((edge) => (direction === 'inbound' ? edge.target === selectedId : edge.source === selectedId))
    .map((edge) => {
      const relatedId = direction === 'inbound' ? edge.source : edge.target;
      const node = nodesById.get(relatedId);
      return node ? { node, edge } : null;
    })
    .filter((item): item is SourceNetworkItem => item !== null)
    .sort((a, b) => b.edge.weight - a.edge.weight || a.node.label.localeCompare(b.node.label))
    .slice(0, 12);
}

function SourceNetworkPanel({
  inbound,
  outbound,
  onOpenProfile,
}: {
  inbound: SourceNetworkItem[];
  outbound: SourceNetworkItem[];
  onOpenProfile: (sourceId: number, domain: string) => void;
}) {
  return (
    <aside className="border-t pt-5 xl:border-t-0 xl:border-l xl:pt-0 xl:pl-5" aria-label="Source network">
      <div className="flex items-center justify-between pb-3">
        <h4 className="font-medium">Network</h4>
        <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">{inbound.length + outbound.length}</span>
      </div>
      <SourceNetworkSection title="Referenced by" items={inbound} onOpenProfile={onOpenProfile} />
      <SourceNetworkSection title="References" items={outbound} onOpenProfile={onOpenProfile} />
    </aside>
  );
}

function SourceNetworkSection({
  title,
  items,
  onOpenProfile,
}: {
  title: string;
  items: SourceNetworkItem[];
  onOpenProfile: (sourceId: number, domain: string) => void;
}) {
  return (
    <section className="border-t py-4">
      <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</h4>
      {items.length === 0 ? (
        <p className="py-3 text-center text-muted-foreground" title="No visible sources.">—</p>
      ) : (
        <div className="space-y-1">
          {items.map((item) => {
            const sourceId = Number(item.node.id.replace('source:', ''));
            return (
              <button className="grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-3 rounded-md px-2 py-2 text-left text-sm hover:bg-muted" key={`${item.edge.source}-${item.edge.target}`} type="button" onClick={() => onOpenProfile(sourceId, item.node.domain)}>
                <span className="min-w-0">
                  <strong className="block truncate font-medium">{item.node.label}</strong>
                  <small className="block truncate text-muted-foreground">{item.node.domain}</small>
                </span>
                <em className="text-xs not-italic text-muted-foreground">{sourceNetworkWeightLabel(item.edge.weight)}</em>
              </button>
            );
          })}
        </div>
      )}
    </section>
  );
}

function sourceNetworkWeightLabel(weight: number) {
  const count = Math.round(weight);
  return `${count} link${count === 1 ? '' : 's'}`;
}

function TableSkeleton({ rows }: { rows: number }) {
  const columns = 'grid-cols-[minmax(8rem,0.8fr)_minmax(16rem,2fr)_repeat(4,5.5rem)_7rem]';
  return (
    <DenseTableViewport aria-label="Loading rows">
      <div className="min-w-[880px]">
        <div className={`${denseTableHeaderClass} ${columns}`} aria-hidden="true">
          {['Source', 'About', 'Essays', 'Essay refs', 'Sources', 'Docs', 'Updated'].map((label) => <span key={label}>{label}</span>)}
        </div>
        {Array.from({ length: rows }).map((_, row) => (
          <div className={`${denseTableRowClass} ${columns}`} key={row}>
            {Array.from({ length: 7 }).map((__, column) => (
              <span className="h-4 animate-pulse rounded bg-muted" key={column} />
            ))}
          </div>
        ))}
      </div>
    </DenseTableViewport>
  );
}

function SourceProfileSkeleton() {
  return (
    <div className="grid min-h-[30rem] gap-5 xl:grid-cols-[minmax(0,2fr)_minmax(18rem,1fr)]" aria-label="Loading source">
      <div className="grid content-start gap-3 py-5">
        <span className="h-6 w-1/3 animate-pulse rounded bg-muted" />
        <span className="h-4 w-full animate-pulse rounded bg-muted" />
        <span className="h-32 w-full animate-pulse rounded bg-muted" />
      </div>
      <div className="grid content-start gap-3 border-t py-5 xl:border-t-0 xl:border-l xl:pl-5">
        <span className="h-5 w-1/2 animate-pulse rounded bg-muted" />
        <span className="h-12 w-full animate-pulse rounded bg-muted" />
        <span className="h-12 w-full animate-pulse rounded bg-muted" />
      </div>
    </div>
  );
}
