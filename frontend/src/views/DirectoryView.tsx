import { FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import { Box } from '@chakra-ui/react';
import { ArrowUpRight } from 'lucide-react';
import { getAdminDocuments, getAdminSources, getBookshelfCollections, getDirectorySources, getGraph, getSourceProfileAnalysis } from '../api';
import { emptyPage } from '../app/paging';
import { documentPath, navigateTo, type ProfileTarget } from '../app/navigation';
import { CorpusSearchForm } from '../CorpusSearchForm';
import { DenseDocumentTable } from '../components/DenseDocumentTable';
import { OverflowText } from '../components/OverflowText';
import { ProfilePagination, type PageState } from '../components/Pagination';
import { ProfileAnalysisCard } from '../components/ProfileAnalysisCard';
import { Button, StateMessage } from '../components/ui';
import type { AdminSource, BookshelfCollection, BookshelfEntry, DirectorySource, DirectorySourceSort, Document, GraphEdge, GraphNode, GraphResponse, Page, SortDirection, SourceProfileAnalysis } from '../types';

type SourceProfileTab = 'profile' | 'essays' | 'collections';

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
  const [selected, setSelected] = useState<ProfileTarget>(target);
  const [documentPageState, setDocumentPageState] = useState<PageState>({ limit: 50, offset: 0 });
  const [directoryPageState, setDirectoryPageState] = useState<PageState>({ limit: 50, offset: 0 });
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const didLoadDirectoryRef = useRef(false);
  const profileCollectionGroups = useMemo(
    () => selected ? sourceCollectionGroups(profileCollections, selected.sourceId, selected.domain) : [],
    [profileCollections, selected?.sourceId, selected?.domain],
  );
  const hasProfileEssays = documentsPage.total > 0;
  const profileNetwork = useMemo(
    () => selected && profileGraph ? sourceNetwork(profileGraph, `source:${selected.sourceId}`) : { inbound: [], outbound: [] },
    [profileGraph, selected?.sourceId],
  );

  useEffect(() => {
    if (activeProfileTab === 'collections' && profileCollectionGroups.length === 0) setActiveProfileTab('profile');
    if (activeProfileTab === 'essays' && !hasProfileEssays) setActiveProfileTab('profile');
  }, [activeProfileTab, hasProfileEssays, profileCollectionGroups.length]);

  useEffect(() => {
    setSelected(target);
    if (target) setQuery(target.domain);
  }, [target?.sourceId, target?.domain]);

  async function refresh(
    nextQuery = query,
    nextSelected = selected,
    nextPage = documentPageState,
    nextDirectoryPage = directoryPageState,
    nextSort = directorySort,
    nextSortDirection = directorySortDirection,
  ) {
    const firstLoad = !didLoadDirectoryRef.current;
    setLoading(firstLoad);
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
        setSelected(null);
        setDocumentsPage(emptyPage<Document>());
        setProfileAnalysis(null);
        setProfileCollections([]);
        setProfileGraph(null);
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
      setSelected(nextProfile);
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
      setRefreshing(false);
    }
  }

  useEffect(() => {
    const nextPage = { limit: 50, offset: 0 };
    setDocumentPageState(nextPage);
    const nextDirectoryPage = { limit: directoryPageState.limit, offset: 0 };
    setDirectoryPageState(nextDirectoryPage);
    refresh(target?.domain ?? '', target, nextPage, nextDirectoryPage);
  }, [target?.sourceId, target?.domain]);

  useEffect(() => {
    if (selected) return;
    const timeout = window.setTimeout(() => {
      const nextDirectoryPage = { limit: directoryPageState.limit, offset: 0 };
      setDirectoryPageState(nextDirectoryPage);
      refresh(query, null, documentPageState, nextDirectoryPage);
    }, 160);
    return () => window.clearTimeout(timeout);
  }, [query, selected?.domain]);

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
    const nextPage = { limit: documentPageState.limit, offset: 0 };
    const nextProfile = { sourceId: source.id, domain: source.canonical_domain };
    setQuery(source.canonical_domain);
    setSelected(nextProfile);
    setActiveProfileTab('profile');
    setDocumentPageState(nextPage);
    refresh(source.canonical_domain, nextProfile, nextPage);
    onOpenProfile(source.id, source.canonical_domain);
  }

  function pageProfileDocuments(nextPage: PageState) {
    setDocumentPageState(nextPage);
    refresh(selected?.domain ?? query, selected, nextPage);
  }

  function updateDirectorySort(nextSort: DirectorySourceSort) {
    const nextPage = { limit: directoryPageState.limit, offset: 0 };
    const nextDirection: SortDirection = nextSort === directorySort ? (directorySortDirection === 'desc' ? 'asc' : 'desc') : defaultDirectorySortDirection(nextSort);
    setDirectorySort(nextSort);
    setDirectorySortDirection(nextDirection);
    setDirectoryPageState(nextPage);
    refresh(query, selected, documentPageState, nextPage, nextSort, nextDirection);
  }

  function pageDirectory(nextPage: PageState) {
    setDirectoryPageState(nextPage);
    refresh(query, selected, documentPageState, nextPage);
  }

  function selectDirectorySource(source: DirectorySource) {
    openSourceProfile({
      id: source.id,
      canonical_domain: source.canonical_domain,
    });
  }

  function showDirectoryRoot() {
    setSelected(null);
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
    navigateTo(documentPath(document.id));
  }

  return (
    <Box as="section" className="directory-view">
      {selected ? (
        <Button className="directory-back directory-back-top" uiVariant="plainIcon" type="button" onClick={showDirectoryRoot} aria-label="Back to sources">
          ←
        </Button>
      ) : (
        <CorpusSearchForm
          className="search-box"
          value={query}
          onChange={updateQuery}
          onSubmit={submit}
          placeholder={loading ? 'Loading...' : 'Filter sources...'}
          disabled={loading}
        />
      )}

      {error && <StateMessage className="error" tone="error">{error}</StateMessage>}
      {loading && <TableSkeleton columns={7} rows={10} />}

      {!loading && !selected && (
        <div className="directory-table-panel">
          <div className={refreshing ? 'directory-table directory-table-refreshing' : 'directory-table'}>
            <div className="directory-table-row directory-table-head" role="row">
              <Button uiVariant="rowAction" type="button" onClick={() => updateDirectorySort('source')}>{directorySortLabel('Source', 'source', directorySort, directorySortDirection)}</Button>
              <span>About</span>
              <Button uiVariant="rowAction" type="button" onClick={() => updateDirectorySort('essays')}>{directorySortLabel('Essays', 'essays', directorySort, directorySortDirection)}</Button>
              <Button uiVariant="rowAction" type="button" onClick={() => updateDirectorySort('essay_references')} data-tooltip="Distinct indexed essays referenced by this source">{directorySortLabel('Essay refs', 'essay_references', directorySort, directorySortDirection)}</Button>
              <Button uiVariant="rowAction" type="button" onClick={() => updateDirectorySort('external_sources')} data-tooltip="Distinct external indexed sources referenced by this source">{directorySortLabel('Sources', 'external_sources', directorySort, directorySortDirection)}</Button>
              <Button uiVariant="rowAction" type="button" onClick={() => updateDirectorySort('documents')}>{directorySortLabel('Docs', 'documents', directorySort, directorySortDirection)}</Button>
              <Button uiVariant="rowAction" type="button" onClick={() => updateDirectorySort('recent')}>{directorySortLabel('Updated', 'recent', directorySort, directorySortDirection)}</Button>
            </div>
            {directoryPage.items.map((source) => (
              <div key={source.id} className="directory-table-row" role="button" tabIndex={0} onClick={() => selectDirectorySource(source)} onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') selectDirectorySource(source);
              }}>
                <span className="directory-source-cell" data-label="Source">
                  <strong>{source.canonical_domain}</strong>
                  <a href={source.url} target="_blank" rel="noreferrer" aria-label="Open source" onClick={(event) => event.stopPropagation()}>
                    <ArrowUpRight size={15} />
                  </a>
                </span>
                <span className="directory-description-cell tooltip-overflow-cell" data-label="About">
                  <OverflowText>{source.description || source.name || '-'}</OverflowText>
                </span>
                <span className="directory-stat-pair" data-label="Essays">
                  <strong>{formatCompactCount(source.essay_count)}</strong>
                </span>
                <span className="directory-stat-pair" data-label="Essay refs">
                  <strong>{formatCompactCount(source.essay_reference_count)}</strong>
                </span>
                <span className="directory-stat-pair" data-label="Sources">
                  <strong>{formatCompactCount(source.external_source_count)}</strong>
                </span>
                <span className="directory-stat-pair" data-label="Docs">
                  <strong>{formatCompactCount(source.document_count)}</strong>
                </span>
                <span className="directory-stat-pair" data-label="Updated">
                  <strong>{formatDirectoryDate(source.last_checked_at)}</strong>
                </span>
              </div>
            ))}
          </div>
          <ProfilePagination page={directoryPage} onChange={pageDirectory} />
        </div>
      )}

      {!loading && selected && (
        <div className="profile-panel directory-profile-page">
          <div className="profile-heading">
            <div>
              <h3>
                <span>{profileAnalysis?.display_name || selectedSource?.canonical_domain || selected.domain}</span>
                <a href={selectedSource?.url ?? `https://${selected.domain}`} target="_blank" rel="noreferrer" aria-label="Open source">
                  <ArrowUpRight size={16} />
                </a>
              </h3>
              {profileAnalysis?.display_name && profileAnalysis.display_name !== selected.domain && <p>{selectedSource?.canonical_domain ?? selected.domain}</p>}
            </div>
          </div>
          <div className="profile-tabs" role="tablist" aria-label="Source profile sections">
            <button className={activeProfileTab === 'profile' ? 'profile-tab profile-tab-active' : 'profile-tab'} type="button" role="tab" aria-selected={activeProfileTab === 'profile'} onClick={() => setActiveProfileTab('profile')}>
              Profile
            </button>
            {hasProfileEssays && (
              <button
                className={activeProfileTab === 'essays' ? 'profile-tab profile-tab-active' : 'profile-tab'}
                type="button"
                role="tab"
                aria-selected={activeProfileTab === 'essays'}
                onClick={() => setActiveProfileTab('essays')}
              >
                Essays <span>{documentsPage.total}</span>
              </button>
            )}
            {profileCollectionGroups.length > 0 && (
              <button
                className={activeProfileTab === 'collections' ? 'profile-tab profile-tab-active' : 'profile-tab'}
                type="button"
                role="tab"
                aria-selected={activeProfileTab === 'collections'}
                onClick={() => setActiveProfileTab('collections')}
              >
                Collections <span>{profileCollectionGroups.length}</span>
              </button>
            )}
          </div>
          {activeProfileTab === 'profile' && (
            <div className="profile-overview-grid">
              <ProfileAnalysisCard analysis={profileAnalysis} />
              <SourceNetworkPanel inbound={profileNetwork.inbound} outbound={profileNetwork.outbound} onOpenProfile={onOpenProfile} />
            </div>
          )}
          {activeProfileTab === 'essays' && (
            <>
              <div className="profile-documents">
                <DirectoryDocumentTable documents={documentsPage.items} onOpenDocument={openDirectoryDrawer} />
              </div>
              <ProfilePagination page={documentsPage} onChange={pageProfileDocuments} />
            </>
          )}
          {activeProfileTab === 'collections' && (
            <SourceCollectionsTab groups={profileCollectionGroups} onOpenDocument={openDirectoryDrawer} />
          )}
        </div>
      )}
    </Box>
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
      <StateMessage className="profile-tab-empty">
        No collections include documents from this source.
      </StateMessage>
    );
  }

  return (
    <div className="profile-collection-list">
      {groups.map(({ collection, items }) => (
        <section className="profile-collection-group" key={collection.id}>
          <div className="profile-collection-heading">
            <strong>{collection.name}</strong>
            <span>{items.length}</span>
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
    <aside className="profile-network-panel" aria-label="Source network">
      <div className="profile-network-panel-heading">
        <h4>Network</h4>
        <span>{inbound.length + outbound.length}</span>
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
    <section className="profile-network-section">
      <h4>{title}</h4>
      {items.length === 0 ? (
        <p className="empty-reference-note" data-tooltip="No visible sources.">—</p>
      ) : (
        <div className="profile-network-list">
          {items.map((item) => {
            const sourceId = Number(item.node.id.replace('source:', ''));
            return (
              <button key={`${item.edge.source}-${item.edge.target}`} type="button" onClick={() => onOpenProfile(sourceId, item.node.domain)}>
                <span>
                  <strong>{item.node.label}</strong>
                  <small>{item.node.domain}</small>
                </span>
                <em>{sourceNetworkWeightLabel(item.edge.weight)}</em>
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

function TableSkeleton({ columns, rows }: { columns: number; rows: number }) {
  return (
    <div className="skeleton-table" aria-label="Loading rows">
      {Array.from({ length: rows }).map((_, row) => (
        <div className="skeleton-table-row" style={{ gridTemplateColumns: `minmax(160px, 1fr) repeat(${columns - 1}, 92px)` }} key={row}>
          {Array.from({ length: columns }).map((__, column) => (
            <span className="skeleton-line" key={column} />
          ))}
        </div>
      ))}
    </div>
  );
}
