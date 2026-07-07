import { FormEvent, useEffect, useRef, useState } from 'react';
import { Box } from '@chakra-ui/react';
import { ArrowUpRight } from 'lucide-react';
import { getAdminDocuments, getAdminSources, getDirectorySources, getDocument, getSourceProfileAnalysis } from '../api';
import { emptyPage } from '../app/paging';
import type { ProfileTarget } from '../app/navigation';
import { CorpusSearchForm } from '../CorpusSearchForm';
import { DenseDocumentTable } from '../components/DenseDocumentTable';
import { ProfilePagination, type PageState } from '../components/Pagination';
import { ProfileAnalysisCard } from '../components/ProfileAnalysisCard';
import { Button, StateMessage } from '../components/ui';
import type { AdminSource, DirectorySource, DirectorySourceSort, Document, DocumentDetail, Page, SortDirection, SourceProfileAnalysis } from '../types';

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

function formatYield(source: DirectorySource) {
  if (!source.document_count) return '-';
  return `${Math.round((source.essay_count / source.document_count) * 100)}%`;
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
  const [directorySort, setDirectorySort] = useState<DirectorySourceSort>('inbound');
  const [directorySortDirection, setDirectorySortDirection] = useState<SortDirection>('desc');
  const [documentsPage, setDocumentsPage] = useState<Page<Document>>(emptyPage);
  const [profileAnalysis, setProfileAnalysis] = useState<SourceProfileAnalysis | null>(null);
  const [drawerDocument, setDrawerDocument] = useState<Document | null>(null);
  const [drawerDetail, setDrawerDetail] = useState<DocumentDetail | null>(null);
  const [drawerLoading, setDrawerLoading] = useState(false);
  const [drawerError, setDrawerError] = useState<string | null>(null);
  const [drawerClosing, setDrawerClosing] = useState(false);
  const [selected, setSelected] = useState<ProfileTarget>(target);
  const [documentPageState, setDocumentPageState] = useState<PageState>({ limit: 50, offset: 0 });
  const [directoryPageState, setDirectoryPageState] = useState<PageState>({ limit: 50, offset: 0 });
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const didLoadDirectoryRef = useRef(false);
  const drawerCloseTimeoutRef = useRef<number | null>(null);

  useEffect(() => {
    setSelected(target);
    if (target) setQuery(target.domain);
  }, [target?.sourceId, target?.domain]);

  useEffect(() => {
    return () => {
      if (drawerCloseTimeoutRef.current !== null) window.clearTimeout(drawerCloseTimeoutRef.current);
    };
  }, []);

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
      const [documents, analysis] = nextProfile
        ? await Promise.all([
            getAdminDocuments({ ...nextPage, sourceId: nextProfile.sourceId, documentType: 'essay' }),
            getSourceProfileAnalysis(nextProfile.sourceId).catch(() => null),
          ])
        : [emptyPage<Document>(), null];
      setDocumentsPage(documents);
      setProfileAnalysis(analysis);
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

  useEffect(() => {
    if (!drawerDocument) {
      setDrawerDetail(null);
      setDrawerError(null);
      return;
    }
    let cancelled = false;
    setDrawerLoading(true);
    setDrawerError(null);
    getDocument(drawerDocument.id)
      .then((detail) => {
        if (!cancelled) setDrawerDetail(detail);
      })
      .catch((err) => {
        if (!cancelled) setDrawerError(err instanceof Error ? err.message : 'Could not load document');
      })
      .finally(() => {
        if (!cancelled) setDrawerLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [drawerDocument?.id]);

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
    setDrawerDocument(null);
    setDocumentsPage(emptyPage<Document>());
    setQuery('');
    onDirectoryRoot();
    if (directoryPage.items.length === 0) {
      refresh('', null, documentPageState, { ...directoryPageState, offset: 0 });
    }
  }

  function openDirectoryDrawer(document: Document) {
    if (drawerCloseTimeoutRef.current !== null) window.clearTimeout(drawerCloseTimeoutRef.current);
    drawerCloseTimeoutRef.current = null;
    setDrawerClosing(false);
    setDrawerDocument(document);
  }

  function closeDirectoryDrawer() {
    if (!drawerDocument || drawerClosing) return;
    setDrawerClosing(true);
    drawerCloseTimeoutRef.current = window.setTimeout(() => {
      setDrawerDocument(null);
      setDrawerClosing(false);
      drawerCloseTimeoutRef.current = null;
    }, 190);
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
      {loading && <TableSkeleton columns={8} rows={10} />}

      {!loading && !selected && (
        <div className="directory-table-panel">
          <div className={refreshing ? 'directory-table directory-table-refreshing' : 'directory-table'}>
            <div className="directory-table-row directory-table-head" role="row">
              <Button uiVariant="rowAction" type="button" onClick={() => updateDirectorySort('source')}>{directorySortLabel('Source', 'source', directorySort, directorySortDirection)}</Button>
              <span>About</span>
              <Button uiVariant="rowAction" type="button" onClick={() => updateDirectorySort('inbound')}>{directorySortLabel('In', 'inbound', directorySort, directorySortDirection)}</Button>
              <Button uiVariant="rowAction" type="button" onClick={() => updateDirectorySort('outbound')}>{directorySortLabel('Out', 'outbound', directorySort, directorySortDirection)}</Button>
              <Button uiVariant="rowAction" type="button" onClick={() => updateDirectorySort('essays')}>{directorySortLabel('Essays', 'essays', directorySort, directorySortDirection)}</Button>
              <Button uiVariant="rowAction" type="button" onClick={() => updateDirectorySort('documents')}>{directorySortLabel('Docs', 'documents', directorySort, directorySortDirection)}</Button>
              <span>Yield</span>
              <Button uiVariant="rowAction" type="button" onClick={() => updateDirectorySort('recent')}>{directorySortLabel('Checked', 'recent', directorySort, directorySortDirection)}</Button>
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
                <span className="directory-description-cell tooltip-overflow-cell" data-label="About" data-tooltip={source.description || source.name || 'No description'}>
                  <span className="tooltip-overflow-text">{source.description || source.name || '-'}</span>
                </span>
                <span className="directory-stat-pair" data-label="In">
                  <strong>{formatCompactCount(source.inbound_count)}</strong>
                </span>
                <span className="directory-stat-pair" data-label="Out">
                  <strong>{formatCompactCount(source.outbound_count)}</strong>
                </span>
                <span className="directory-stat-pair" data-label="Essays">
                  <strong>{formatCompactCount(source.essay_count)}</strong>
                </span>
                <span className="directory-stat-pair" data-label="Docs">
                  <strong>{formatCompactCount(source.document_count)}</strong>
                </span>
                <span className="directory-stat-pair" data-label="Yield">
                  <strong>{formatYield(source)}</strong>
                </span>
                <span className="directory-stat-pair" data-label="Checked">
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
              <h3>{profileAnalysis?.display_name || selectedSource?.canonical_domain || selected.domain}</h3>
              {profileAnalysis?.display_name && profileAnalysis.display_name !== selected.domain && <p>{selectedSource?.canonical_domain ?? selected.domain}</p>}
            </div>
            <a href={selectedSource?.url ?? `https://${selected.domain}`} target="_blank" rel="noreferrer">
              <ArrowUpRight size={16} />
            </a>
          </div>
          <ProfileAnalysisCard analysis={profileAnalysis} />
          <div className="profile-documents">
            <DirectoryDocumentTable documents={documentsPage.items} onOpenDocument={openDirectoryDrawer} />
          </div>
          <ProfilePagination page={documentsPage} onChange={pageProfileDocuments} />
        </div>
      )}
      {drawerDocument && (
        <>
          <button className={drawerClosing ? 'drawer-backdrop drawer-closing' : 'drawer-backdrop'} type="button" aria-label="Close details" onClick={closeDirectoryDrawer} />
          <DirectoryDocumentDrawer
            document={drawerDetail ?? drawerDocument}
            loading={drawerLoading}
            error={drawerError}
            closing={drawerClosing}
            onClose={closeDirectoryDrawer}
          />
        </>
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
      onPrimaryClick={(row) => onOpenDocument(row.document)}
    />
  );
}

function DirectoryDocumentDrawer({
  document,
  loading,
  error,
  closing,
  onClose,
}: {
  document: Document | DocumentDetail;
  loading: boolean;
  error: string | null;
  closing: boolean;
  onClose: () => void;
}) {
  const detail = 'outgoing_links' in document ? document : null;
  return (
    <aside className={closing ? 'bookshelf-detail-drawer directory-document-drawer drawer-closing' : 'bookshelf-detail-drawer directory-document-drawer'} aria-label="Directory document details">
      <div className="bookshelf-detail-header">
        <div>
          <span>{document.source_domain}</span>
          <h3>
            {document.title ?? document.url}
            <a href={document.url} target="_blank" rel="noreferrer" aria-label="Open document">
              <ArrowUpRight size={15} />
            </a>
          </h3>
        </div>
        <button type="button" onClick={onClose} aria-label="Close details">×</button>
      </div>

      {loading && <div className="skeleton-stack" aria-label="Loading document details"><span className="skeleton-line" /><span className="skeleton-line" /><span className="skeleton-line" /></div>}
      {error && <StateMessage className="error" tone="error">{error}</StateMessage>}

      {document.topics.length > 0 && (
        <div className="bookshelf-detail-tags directory-document-drawer-tags">
          {document.topics.map((topic) => <span key={topic}>{topic}</span>)}
        </div>
      )}

      <section className="bookshelf-detail-section">
        <h4>Summary</h4>
        <p>{document.summary || 'No summary yet.'}</p>
      </section>

      <div className="bookshelf-detail-reference-grid">
        <section className="bookshelf-detail-section">
          <h4>References</h4>
          {detail?.outgoing_links.length ? (
            <div className="bookshelf-detail-link-list">
              {detail.outgoing_links.map((link, index) => (
                <a key={`${link.target_url}-${index}`} href={link.target_url} target="_blank" rel="noreferrer">
                  <strong>{link.anchor_text || link.target_domain || link.target_url}</strong>
                  <small>{link.target_domain || link.target_url}</small>
                  {link.context && <span>{link.context}</span>}
                </a>
              ))}
            </div>
          ) : (
            <p>No outgoing references indexed.</p>
          )}
        </section>
        <section className="bookshelf-detail-section">
          <h4>Referenced By</h4>
          {detail?.incoming_links.length ? (
            <div className="bookshelf-detail-link-list">
              {detail.incoming_links.map((link, index) => (
                <button key={`${link.source_document_id}-${index}`} type="button">
                  <strong>{link.anchor_text || `Document ${link.source_document_id}`}</strong>
                  <small>{link.target_url}</small>
                </button>
              ))}
            </div>
          ) : (
            <p>No incoming references indexed.</p>
          )}
        </section>
      </div>
    </aside>
  );
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
