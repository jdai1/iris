import { FormEvent, lazy, ReactNode, Suspense, useEffect, useMemo, useRef, useState } from 'react';
import { ArrowUpRight, FileText, Folder, GitFork, LayoutTemplate, Orbit } from 'lucide-react';
import { getAdminDocuments, getAdminSources, getBookshelfCollections, getDirectorySources, getGraph, getSourceProfileAnalysis } from '../api';
import { GraphExplorer } from '../GraphExplorer';
import { emptyPage } from '../app/paging';
import { documentPath, navigateTo, type ProfileTarget } from '../app/navigation';
import { CorpusSearchForm } from '../CorpusSearchForm';
import { DenseDocumentTable } from '../components/DenseDocumentTable';
import { OverflowText } from '../components/OverflowText';
import { ProfilePagination, type PageState } from '../components/Pagination';
import { ProfileAnalysisCard } from '../components/ProfileAnalysisCard';
import { Button, StateMessage } from '../components/ui';
import type { AdminSource, BookshelfCollection, BookshelfEntry, DirectorySource, DirectorySourceSort, Document, GraphEdge, GraphNode, GraphResponse, Page, SortDirection, SourceProfileAnalysis } from '../types';

type SourceProfileTab = 'profile' | 'essays' | 'collections' | 'explore' | 'graph';

const EmbeddingExplorer = lazy(() =>
  import('../EmbeddingExplorer').then((module) => ({ default: module.EmbeddingExplorer })),
);

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

export function DirectoryView({
  target,
  onOpenProfile,
  onDirectoryRoot,
}: {
  target: ProfileTarget;
  onOpenProfile: (sourceId: number, domain: string) => void;
  onDirectoryRoot: () => void;
}) {
  const [query, setQuery] = useState(target?.domain ?? '');
  const [selectedSource, setSelectedSource] = useState<AdminSource | null>(null);
  const [directoryPage, setDirectoryPage] = useState<Page<DirectorySource>>(emptyPage);
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
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const didLoadDirectoryRef = useRef(false);
  const sourceLoadKeyRef = useRef<string | null>(null);
  const profileCollectionGroups = useMemo(
    () => target ? sourceCollectionGroups(profileCollections, target.sourceId, target.domain) : [],
    [profileCollections, target?.sourceId, target?.domain],
  );
  const activeSelectedSource = selectedSource?.canonical_domain === target?.domain ? selectedSource : null;
  const resolvedSourceId = activeSelectedSource?.id ?? target?.sourceId ?? 0;
  const profileNetwork = useMemo(
    () => target && profileGraph ? sourceNetwork(profileGraph, `source:${resolvedSourceId}`) : { inbound: [], outbound: [] },
    [profileGraph, resolvedSourceId, target?.domain],
  );

  useEffect(() => {
    setActiveProfileTab('profile');
    if (target) {
      setQuery(target.domain);
      setProfileLoading(true);
    }
  }, [target?.sourceId, target?.domain]);

  async function refresh(
    nextQuery = query,
    nextSelected = target,
    nextPage = documentPageState,
    nextDirectoryPage = directoryPageState,
    nextSort = directorySort,
    nextSortDirection = directorySortDirection,
  ) {
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
          q: normalizedQuery,
          sort: nextSort,
          direction: nextSortDirection,
          ...nextDirectoryPage,
        });
        setDirectoryPage(tablePage);
        setSelectedSource(null);
        setDocumentsPage(emptyPage<Document>());
        setProfileAnalysis(null);
        setProfileCollections([]);
        setProfileGraph(null);
        setProfileLoading(false);
        return;
      }
      const sources = await getAdminSources({ status: 'indexed', q: normalizedQuery, limit: 25 });
      const source =
        (nextSelected?.sourceId ? sources.items.find((item) => item.id === nextSelected.sourceId) : null) ??
        sources.items.find((item) => item.canonical_domain === normalizedQuery.toLowerCase()) ??
        (normalizedQuery ? sources.items[0] : null) ??
        null;
      const nextProfile = source ? { sourceId: source.id, domain: source.canonical_domain } : null;
      setSelectedSource(source);
      if (source && !nextSelected) setQuery(source.canonical_domain);
      const [documents, analysis, collections, graph] = nextProfile
        ? await Promise.all([
            getAdminDocuments({ ...nextPage, sourceId: nextProfile.sourceId, documentType: 'essay' }),
            getSourceProfileAnalysis(nextProfile.sourceId).catch(() => null),
            getBookshelfCollections().catch(() => []),
            getGraph({ mode: 'sources', sourceId: nextProfile.sourceId, limit: 80, depth: 1 }).catch(() => null),
          ])
        : [emptyPage<Document>(), null, [], null];
      setDocumentsPage(documents);
      setProfileAnalysis(analysis);
      setProfileCollections(collections);
      setProfileGraph(graph);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Directory failed');
    } finally {
      didLoadDirectoryRef.current = true;
      setLoading(false);
      setProfileLoading(false);
      setRefreshing(false);
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
    const nextDirectoryPage = { limit: directoryPageState.limit, offset: 0 };
    setDirectoryPageState(nextDirectoryPage);
    refresh(target.domain, target, nextPage, nextDirectoryPage);
  }, [target?.sourceId, target?.domain]);

  useEffect(() => {
    if (target) return;
    const timeout = window.setTimeout(() => {
      const nextDirectoryPage = { limit: directoryPageState.limit, offset: 0 };
      setDirectoryPageState(nextDirectoryPage);
      refresh(query, null, documentPageState, nextDirectoryPage);
    }, 160);
    return () => window.clearTimeout(timeout);
  }, [query, target?.domain]);

  function submit(event: FormEvent) {
    event.preventDefault();
    const nextPage = { limit: documentPageState.limit, offset: 0 };
    const nextDirectoryPage = { limit: directoryPageState.limit, offset: 0 };
    setDocumentPageState(nextPage);
    setDirectoryPageState(nextDirectoryPage);
    refresh(query, null, nextPage, nextDirectoryPage);
  }

  function updateQuery(value: string) {
    setQuery(value);
  }

  function openSourceProfile(source: Pick<AdminSource, 'id' | 'canonical_domain'>) {
    setQuery(source.canonical_domain);
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
    refresh(target?.domain ?? query, target, nextPage);
  }

  function updateDirectorySort(nextSort: DirectorySourceSort) {
    const nextPage = { limit: directoryPageState.limit, offset: 0 };
    const nextDirection: SortDirection = nextSort === directorySort ? (directorySortDirection === 'desc' ? 'asc' : 'desc') : defaultDirectorySortDirection(nextSort);
    setDirectorySort(nextSort);
    setDirectorySortDirection(nextDirection);
    setDirectoryPageState(nextPage);
    refresh(query, target, documentPageState, nextPage, nextSort, nextDirection);
  }

  function pageDirectory(nextPage: PageState) {
    setDirectoryPageState(nextPage);
    refresh(query, target, documentPageState, nextPage);
  }

  function selectDirectorySource(source: DirectorySource) {
    openSourceProfile({
      id: source.id,
      canonical_domain: source.canonical_domain,
    });
  }

  function showDirectoryRoot() {
    setSelectedSource(null);
    setProfileAnalysis(null);
    setProfileCollections([]);
    setProfileGraph(null);
    setActiveProfileTab('profile');
    setDocumentsPage(emptyPage<Document>());
    setQuery('');
    onDirectoryRoot();
    if (directoryPage.items.length === 0) {
      refresh('', null, documentPageState, { ...directoryPageState, offset: 0 });
    }
  }

  function openDirectoryDrawer(document: Document) {
    navigateTo(documentPath(document.uuid));
  }

  return (
    <section className="min-h-svh min-w-0 p-4 sm:p-6">
      {target ? (
        <Button className="mb-4 size-9 rounded-md border bg-background" uiVariant="plainIcon" type="button" onClick={showDirectoryRoot} aria-label="Back to sources">
          ←
        </Button>
      ) : (
        <CorpusSearchForm
          className="mb-5 w-full max-w-xl"
          value={query}
          onChange={updateQuery}
          onSubmit={submit}
          placeholder={loading ? 'Loading...' : 'Filter sources...'}
          disabled={loading}
        />
      )}

      {error && <StateMessage className="mb-5" tone="error">{error}</StateMessage>}
      {loading && !target && <TableSkeleton rows={10} />}

      {!loading && !target && (
        <div className="overflow-x-auto border-y">
          <div className={`min-w-[880px] transition-opacity ${refreshing ? 'opacity-60' : 'opacity-100'}`}>
            <div className="grid grid-cols-[minmax(12rem,1.2fr)_minmax(16rem,2fr)_repeat(4,5.5rem)_7rem] items-center gap-3 border-b bg-muted/40 px-4 py-2 text-xs font-semibold uppercase text-muted-foreground" role="row">
              <Button uiVariant="rowAction" type="button" onClick={() => updateDirectorySort('source')}>{directorySortLabel('Source', 'source', directorySort, directorySortDirection)}</Button>
              <span>About</span>
              <Button uiVariant="rowAction" type="button" onClick={() => updateDirectorySort('essays')}>{directorySortLabel('Essays', 'essays', directorySort, directorySortDirection)}</Button>
              <Button uiVariant="rowAction" type="button" onClick={() => updateDirectorySort('essay_references')} data-tooltip="Distinct indexed essays referenced by this source">{directorySortLabel('Essay refs', 'essay_references', directorySort, directorySortDirection)}</Button>
              <Button uiVariant="rowAction" type="button" onClick={() => updateDirectorySort('external_sources')} data-tooltip="Distinct external indexed sources referenced by this source">{directorySortLabel('Sources', 'external_sources', directorySort, directorySortDirection)}</Button>
              <Button uiVariant="rowAction" type="button" onClick={() => updateDirectorySort('documents')}>{directorySortLabel('Docs', 'documents', directorySort, directorySortDirection)}</Button>
              <Button uiVariant="rowAction" type="button" onClick={() => updateDirectorySort('recent')}>{directorySortLabel('Updated', 'recent', directorySort, directorySortDirection)}</Button>
            </div>
            {directoryPage.items.map((source) => (
              <div key={source.id} className="grid cursor-pointer grid-cols-[minmax(12rem,1.2fr)_minmax(16rem,2fr)_repeat(4,5.5rem)_7rem] items-center gap-3 border-b px-4 py-3 text-sm last:border-0 hover:bg-muted/50" role="button" tabIndex={0} onClick={() => selectDirectorySource(source)} onKeyDown={(event) => {
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
          </div>
          <ProfilePagination page={directoryPage} onChange={pageDirectory} />
        </div>
      )}

      {target && (
        <div className="min-h-[calc(100svh-5rem)]" aria-busy={profileLoading}>
          <div className="flex h-16 items-center border-b px-5">
            <div>
              <h3 className="flex items-center gap-2 text-lg font-semibold">
                <span>{activeSelectedSource?.canonical_domain || target.domain}</span>
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
              count={profileLoading ? null : documentsPage.total}
              onClick={() => setActiveProfileTab('essays')}
            />
            <SourceViewButton
              active={activeProfileTab === 'collections'}
              icon={<Folder size={14} />}
              label="Collections"
              count={profileLoading ? null : profileCollectionGroups.length}
              onClick={() => setActiveProfileTab('collections')}
            />
            <SourceViewButton
              active={activeProfileTab === 'explore'}
              icon={<Orbit size={14} />}
              label="Explore"
              onClick={() => setActiveProfileTab('explore')}
            />
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
                <div className="overflow-x-auto">
                  <DirectoryDocumentTable documents={documentsPage.items} onOpenDocument={openDirectoryDrawer} />
                </div>
                <ProfilePagination page={documentsPage} onChange={pageProfileDocuments} />
              </>
            )}
            {!profileLoading && activeProfileTab === 'collections' && (
              <SourceCollectionsTab groups={profileCollectionGroups} onOpenDocument={openDirectoryDrawer} />
            )}
            {!profileLoading && activeProfileTab === 'explore' && activeSelectedSource && (
              <div className="min-h-[calc(100svh-15rem)] overflow-hidden rounded-xl border">
                <Suspense fallback={<SourceVisualSkeleton />}>
                  <EmbeddingExplorer key={activeSelectedSource.id} sourceId={activeSelectedSource.id} />
                </Suspense>
              </div>
            )}
            {!profileLoading && activeProfileTab === 'graph' && (
              <div className="min-h-[calc(100svh-15rem)] overflow-hidden rounded-xl border">
                <GraphExplorer
                  key={target.domain}
                  onOpenProfile={onOpenProfile}
                  initialDomain={target.domain}
                />
              </div>
            )}
          </div>
        </div>
      )}
    </section>
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
  return (
    <div className="overflow-hidden border-y" aria-label="Loading rows">
      {Array.from({ length: rows }).map((_, row) => (
        <div className="grid grid-cols-[minmax(160px,1fr)_repeat(6,92px)] gap-3 border-b px-4 py-3 last:border-0" key={row}>
          {Array.from({ length: 7 }).map((__, column) => (
            <span className="h-4 animate-pulse rounded bg-muted" key={column} />
          ))}
        </div>
      ))}
    </div>
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

function SourceVisualSkeleton() {
  return (
    <div className="grid min-h-[30rem] place-items-center" aria-label="Loading visualization">
      <span className="size-10 animate-pulse rounded-full bg-muted" />
    </div>
  );
}
