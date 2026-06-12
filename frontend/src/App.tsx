import { FormEvent, useEffect, useMemo, useState } from 'react';
import { ArrowUpRight, BookOpen, Check, Database, LayoutDashboard, Play, Plus, Search, Sparkles, X } from 'lucide-react';
import {
  createSource,
  crawlSource,
  getAdminCrawlJobs,
  getAdminDocuments,
  getAdminIndexRuns,
  getAdminOverview,
  getAdminSources,
  getDigest,
  getSources,
  searchCorpus,
  sendFeedback,
} from './api';
import type { AdminCrawlJob, AdminIndexRun, AdminOverview, AdminSource, DigestItem, Page, SearchResponse, Source, Document } from './types';

type View = 'search' | 'digest' | 'sources' | 'admin';
type PageState = { limit: number; offset: number };

const emptyPage = <T,>(): Page<T> => ({
  items: [],
  total: 0,
  limit: 50,
  offset: 0,
  has_next: false,
  has_previous: false,
});

function DocumentCard({
  document,
  reason,
  score,
  onFeedback,
}: {
  document: Document;
  reason: string;
  score?: number;
  onFeedback?: (action: string) => void;
}) {
  return (
    <article className="document-card">
      <div className="document-meta">
        <span>{document.source_domain}</span>
        <span>{document.document_type}</span>
        {typeof score === 'number' && <span>{score.toFixed(2)}</span>}
      </div>
      <h3>{document.title ?? document.url}</h3>
      {document.summary && <p className="summary">{document.summary}</p>}
      <p className="reason">{reason}</p>
      <div className="topics">
        {document.topics.slice(0, 6).map((topic) => (
          <span key={topic}>{topic}</span>
        ))}
      </div>
      <div className="card-actions">
        <a href={document.url}>
          <ArrowUpRight size={16} />
          Open
        </a>
        {onFeedback && (
          <>
            <button type="button" onClick={() => onFeedback('save')}>
              <Check size={16} />
              Save
            </button>
            <button type="button" onClick={() => onFeedback('dismiss')}>
              <X size={16} />
              Dismiss
            </button>
          </>
        )}
      </div>
    </article>
  );
}

function SearchView() {
  const [query, setQuery] = useState('');
  const [response, setResponse] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    try {
      setResponse(await searchCorpus(query.trim()));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Search failed');
    } finally {
      setLoading(false);
    }
  }

  async function feedback(documentId: number, action: string) {
    await sendFeedback({
      document_id: documentId,
      surface: 'search',
      action,
      search_id: response?.search_id,
    });
  }

  return (
    <section className="search-view">
      <form className="search-box" onSubmit={submit}>
        <Search size={22} />
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Ask anything across the corpus..."
          autoFocus
        />
        <button type="submit" disabled={loading || !query.trim()}>
          {loading ? 'Searching' : 'Search'}
        </button>
      </form>

      {error && <div className="error">{error}</div>}

      {response && (
        <div className="results-layout">
          <aside className="answer-panel">
            <div className="panel-heading">
              <Sparkles size={18} />
              Synthesis
            </div>
            <p>{response.answer}</p>
          </aside>
          <div className="results-list">
            {response.results.map((result) => (
              <DocumentCard
                key={result.document.id}
                document={result.document}
                reason={result.reason}
                score={result.score}
                onFeedback={(action) => feedback(result.document.id, action)}
              />
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

function DigestView() {
  const [items, setItems] = useState<DigestItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      setItems(await getDigest());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Digest failed');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function feedback(item: DigestItem, action: string) {
    await sendFeedback({
      document_id: item.document.id,
      surface: 'digest',
      action,
      digest_item_id: item.id,
    });
    setItems((current) => current.filter((candidate) => candidate.id !== item.id));
  }

  if (loading) return <div className="empty-state">Loading digest...</div>;

  return (
    <section>
      <div className="section-header">
        <div>
          <h2>Digest</h2>
          <p>Old and new corpus items ranked by fit, quality, and graph signal.</p>
        </div>
        <button type="button" onClick={refresh}>Refresh</button>
      </div>
      <div className="digest-stack">
        {error && <div className="error">{error}</div>}
        {items.map((item) => (
          <DocumentCard
            key={item.id}
            document={item.document}
            reason={item.reason}
            score={item.score}
            onFeedback={(action) => feedback(item, action)}
          />
        ))}
        {items.length === 0 && <div className="empty-state">No digest items yet. Add and crawl a source.</div>}
      </div>
    </section>
  );
}

function SourcesView() {
  const [sources, setSources] = useState<Source[]>([]);
  const [url, setUrl] = useState('');
  const [busyId, setBusyId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setError(null);
    try {
      setSources(await getSources());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sources failed');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function addSource(event: FormEvent) {
    event.preventDefault();
    if (!url.trim()) return;
    setError(null);
    try {
      const source = await createSource(url.trim(), false);
      setUrl('');
      setSources((current) => [source, ...current.filter((item) => item.id !== source.id)]);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Add source failed');
    }
  }

  async function crawl(id: number) {
    setBusyId(id);
    setError(null);
    try {
      await crawlSource(id);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Crawl failed');
    } finally {
      setBusyId(null);
    }
  }

  const byStatus = useMemo(() => {
    return sources.reduce<Record<string, number>>((acc, source) => {
      acc[source.status] = (acc[source.status] ?? 0) + 1;
      return acc;
    }, {});
  }, [sources]);

  return (
    <section>
      <div className="section-header">
        <div>
          <h2>Sources</h2>
          <p>Seeds and automatically discovered linked domains.</p>
        </div>
      </div>
      <form className="source-form" onSubmit={addSource}>
        <input value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://example.com" />
        <button type="submit"><Plus size={16} /> Add</button>
      </form>
      <div className="status-strip">
        {Object.entries(byStatus).map(([status, count]) => (
          <span key={status}>{status}: {count}</span>
        ))}
      </div>
      {error && <div className="error">{error}</div>}
      {loading ? (
        <div className="empty-state">Loading sources...</div>
      ) : (
        <div className="source-list">
          {sources.map((source) => (
            <div className="source-row" key={source.id}>
              <div>
                <strong>{source.canonical_domain}</strong>
                <span>{source.status}{source.rss_url ? ` · RSS` : ''}</span>
              </div>
              <button type="button" onClick={() => crawl(source.id)} disabled={busyId === source.id}>
                <Play size={15} />
                {busyId === source.id ? 'Crawling' : 'Crawl'}
              </button>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function AdminView() {
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [sourcesPage, setSourcesPage] = useState<Page<AdminSource>>(emptyPage);
  const [documentsPage, setDocumentsPage] = useState<Page<Document>>(emptyPage);
  const [jobsPage, setJobsPage] = useState<Page<AdminCrawlJob>>(emptyPage);
  const [runsPage, setRunsPage] = useState<Page<AdminIndexRun>>(emptyPage);
  const [status, setStatus] = useState('indexed');
  const [query, setQuery] = useState('');
  const [documentSourceId, setDocumentSourceId] = useState<number | undefined>(undefined);
  const [documentType, setDocumentType] = useState('all');
  const [jobStatus, setJobStatus] = useState('all');
  const [jobSourceId, setJobSourceId] = useState<number | undefined>(undefined);
  const [jobRunId, setJobRunId] = useState<number | undefined>(undefined);
  const [runStatus, setRunStatus] = useState('all');
  const [sourcePageState, setSourcePageState] = useState<PageState>({ limit: 50, offset: 0 });
  const [documentPageState, setDocumentPageState] = useState<PageState>({ limit: 50, offset: 0 });
  const [jobPageState, setJobPageState] = useState<PageState>({ limit: 50, offset: 0 });
  const [runPageState, setRunPageState] = useState<PageState>({ limit: 50, offset: 0 });
  const [activeTable, setActiveTable] = useState<'sources' | 'documents' | 'jobs' | 'runs'>('sources');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function refresh(
    nextStatus = status,
    nextQuery = query,
    nextDocumentSourceId = documentSourceId,
    nextDocumentType = documentType,
    nextSourcePage = sourcePageState,
    nextDocumentPage = documentPageState,
    nextJobPage = jobPageState,
    nextRunPage = runPageState,
    nextJobStatus = jobStatus,
    nextJobSourceId = jobSourceId,
    nextJobRunId = jobRunId,
    nextRunStatus = runStatus,
  ) {
    setLoading(true);
    setError(null);
    try {
      const [overviewData, sourceData, documentData, jobData, runData] = await Promise.all([
        getAdminOverview(),
        getAdminSources({ status: nextStatus, q: nextQuery.trim(), ...nextSourcePage }),
        getAdminDocuments({ ...nextDocumentPage, sourceId: nextDocumentSourceId, documentType: nextDocumentType }),
        getAdminCrawlJobs({ ...nextJobPage, status: nextJobStatus, sourceId: nextJobSourceId, indexRunId: nextJobRunId }),
        getAdminIndexRuns({ ...nextRunPage, status: nextRunStatus }),
      ]);
      setOverview(overviewData);
      setSourcesPage(sourceData);
      setDocumentsPage(documentData);
      setJobsPage(jobData);
      setRunsPage(runData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Admin data failed');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  function updateStatus(nextStatus: string) {
    const nextPage = { ...sourcePageState, offset: 0 };
    setStatus(nextStatus);
    setSourcePageState(nextPage);
    refresh(nextStatus, query, documentSourceId, documentType, nextPage);
  }

  function submitSearch(event: FormEvent) {
    event.preventDefault();
    const nextPage = { ...sourcePageState, offset: 0 };
    setSourcePageState(nextPage);
    refresh(status, query, documentSourceId, documentType, nextPage);
  }

  function updateDocumentSource(value: string) {
    const nextSourceId = value ? Number(value) : undefined;
    const nextPage = { ...documentPageState, offset: 0 };
    setDocumentSourceId(nextSourceId);
    setDocumentPageState(nextPage);
    refresh(status, query, nextSourceId, documentType, sourcePageState, nextPage);
  }

  function updateDocumentType(nextType: string) {
    const nextPage = { ...documentPageState, offset: 0 };
    setDocumentType(nextType);
    setDocumentPageState(nextPage);
    refresh(status, query, documentSourceId, nextType, sourcePageState, nextPage);
  }

  function pageSources(nextPage: PageState) {
    setSourcePageState(nextPage);
    refresh(status, query, documentSourceId, documentType, nextPage);
  }

  function pageDocuments(nextPage: PageState) {
    setDocumentPageState(nextPage);
    refresh(status, query, documentSourceId, documentType, sourcePageState, nextPage);
  }

  function pageJobs(nextPage: PageState) {
    setJobPageState(nextPage);
    refresh(status, query, documentSourceId, documentType, sourcePageState, documentPageState, nextPage);
  }

  function pageRuns(nextPage: PageState) {
    setRunPageState(nextPage);
    refresh(status, query, documentSourceId, documentType, sourcePageState, documentPageState, jobPageState, nextPage);
  }

  function updateJobStatus(nextStatus: string) {
    const nextPage = { ...jobPageState, offset: 0 };
    setJobStatus(nextStatus);
    setJobPageState(nextPage);
    refresh(status, query, documentSourceId, documentType, sourcePageState, documentPageState, nextPage, runPageState, nextStatus);
  }

  function updateJobSource(value: string) {
    const nextSourceId = value ? Number(value) : undefined;
    const nextPage = { ...jobPageState, offset: 0 };
    setJobSourceId(nextSourceId);
    setJobPageState(nextPage);
    refresh(status, query, documentSourceId, documentType, sourcePageState, documentPageState, nextPage, runPageState, jobStatus, nextSourceId);
  }

  function updateJobRun(value: string) {
    const nextRunId = value ? Number(value) : undefined;
    const nextPage = { ...jobPageState, offset: 0 };
    setJobRunId(nextRunId);
    setJobPageState(nextPage);
    refresh(status, query, documentSourceId, documentType, sourcePageState, documentPageState, nextPage, runPageState, jobStatus, jobSourceId, nextRunId);
  }

  function updateRunStatus(nextStatus: string) {
    const nextPage = { ...runPageState, offset: 0 };
    setRunStatus(nextStatus);
    setRunPageState(nextPage);
    refresh(status, query, documentSourceId, documentType, sourcePageState, documentPageState, jobPageState, nextPage, jobStatus, jobSourceId, jobRunId, nextStatus);
  }

  const crawledSources = overview?.source_statuses.indexed ?? 0;
  const activeSources = overview?.source_statuses.crawling ?? 0;

  return (
    <section>
      <div className="section-header">
        <div>
          <h2>Admin</h2>
          <p>Read-only database view for ingestion, crawl runs, sources, and documents.</p>
        </div>
        <button type="button" onClick={() => refresh()}>
          Refresh
        </button>
      </div>

      {error && <div className="error">{error}</div>}

      <div className="metric-grid">
        <Metric label="sources crawled" value={crawledSources} />
        <Metric label="active crawls" value={activeSources} />
        <Metric label="documents" value={overview?.totals.documents ?? 0} />
        <Metric label="essays" value={overview?.totals.essay_documents ?? 0} />
        <Metric label="links" value={overview?.totals.links ?? 0} />
        <Metric label="resolved links" value={overview?.totals.resolved_links ?? 0} />
      </div>

      <div className="admin-controls">
        <div className="tab-strip">
          {(['sources', 'documents', 'jobs', 'runs'] as const).map((table) => (
            <button
              key={table}
              type="button"
              className={activeTable === table ? 'active' : ''}
              onClick={() => setActiveTable(table)}
            >
              {table}
            </button>
          ))}
        </div>
        {activeTable === 'sources' && (
          <form className="admin-filter" onSubmit={submitSearch}>
            <select value={status} onChange={(event) => updateStatus(event.target.value)}>
              <option value="indexed">crawled/indexed</option>
              <option value="queued">queued</option>
              <option value="ignored">ignored</option>
              <option value="failed">failed</option>
              <option value="crawling">crawling</option>
              <option value="all">all</option>
            </select>
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="filter domain" />
            <button type="submit">Apply</button>
          </form>
        )}
        {activeTable === 'documents' && (
          <div className="admin-filter">
            <select value={documentSourceId ?? ''} onChange={(event) => updateDocumentSource(event.target.value)}>
              <option value="">all sources, newest first</option>
              {sourcesPage.items
                .filter((source) => source.document_count > 0)
                .map((source) => (
                  <option key={source.id} value={source.id}>
                    {source.canonical_domain} ({source.document_count})
                  </option>
                ))}
            </select>
            <select value={documentType} onChange={(event) => updateDocumentType(event.target.value)}>
              <option value="all">all document types</option>
              <option value="essay">essays</option>
              <option value="collection">collections</option>
            </select>
          </div>
        )}
        {activeTable === 'jobs' && (
          <div className="admin-filter admin-filter-wide">
            <select value={jobStatus} onChange={(event) => updateJobStatus(event.target.value)}>
              <option value="all">all job statuses</option>
              <option value="succeeded">succeeded</option>
              <option value="skipped">skipped</option>
              <option value="failed">failed</option>
              <option value="running">running</option>
            </select>
            <select value={jobSourceId ?? ''} onChange={(event) => updateJobSource(event.target.value)}>
              <option value="">all sources</option>
              {sourcesPage.items.map((source) => (
                <option key={source.id} value={source.id}>{source.canonical_domain}</option>
              ))}
            </select>
            <input
              value={jobRunId ?? ''}
              onChange={(event) => updateJobRun(event.target.value)}
              placeholder="index run id"
              inputMode="numeric"
            />
          </div>
        )}
        {activeTable === 'runs' && (
          <div className="admin-filter">
            <select value={runStatus} onChange={(event) => updateRunStatus(event.target.value)}>
              <option value="all">all run statuses</option>
              <option value="succeeded">succeeded</option>
              <option value="stopped">stopped</option>
              <option value="failed">failed</option>
              <option value="running">running</option>
            </select>
          </div>
        )}
      </div>

      {loading ? <div className="empty-state">Loading admin data...</div> : null}
      {!loading && activeTable === 'sources' && (
        <>
          <Pagination page={sourcesPage} onChange={pageSources} />
          <AdminSourcesTable sources={sourcesPage.items} />
          <Pagination page={sourcesPage} onChange={pageSources} />
        </>
      )}
      {!loading && activeTable === 'documents' && (
        <>
          <Pagination page={documentsPage} onChange={pageDocuments} />
          <AdminDocumentsTable
            documents={documentsPage.items}
            page={documentsPage}
            sourceName={sourcesPage.items.find((source) => source.id === documentSourceId)?.canonical_domain}
          />
          <Pagination page={documentsPage} onChange={pageDocuments} />
        </>
      )}
      {!loading && activeTable === 'jobs' && (
        <>
          <Pagination page={jobsPage} onChange={pageJobs} />
          <AdminJobsTable jobs={jobsPage.items} />
          <Pagination page={jobsPage} onChange={pageJobs} />
        </>
      )}
      {!loading && activeTable === 'runs' && (
        <>
          <Pagination page={runsPage} onChange={pageRuns} />
          <AdminRunsTable runs={runsPage.items} />
          <Pagination page={runsPage} onChange={pageRuns} />
        </>
      )}
    </section>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value.toLocaleString()}</strong>
    </div>
  );
}

function AdminSourcesTable({ sources }: { sources: AdminSource[] }) {
  return (
    <div className="admin-table-wrap">
      <table className="admin-table">
        <thead>
          <tr>
            <th>Domain</th>
            <th>Status</th>
            <th>Docs</th>
            <th>Essays</th>
            <th>Latest Crawl</th>
            <th>Why It Stopped</th>
            <th>Checked</th>
          </tr>
        </thead>
        <tbody>
          {sources.map((source) => (
            <tr key={source.id}>
              <td>
                <a href={source.url}>{source.canonical_domain}</a>
                {source.description && <small>{source.description}</small>}
              </td>
              <td><StatusPill value={source.status} /></td>
              <td>{source.document_count}</td>
              <td>{source.essay_count}</td>
              <td>{source.latest_job ? <JobLabel job={source.latest_job} /> : 'none'}</td>
              <td>{source.latest_job?.outcome ?? '-'}</td>
              <td>{formatDate(source.last_checked_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {sources.length === 0 && <div className="empty-state">No sources match this filter.</div>}
    </div>
  );
}

function AdminDocumentsTable({ documents, page, sourceName }: { documents: Document[]; page: Page<Document>; sourceName?: string }) {
  return (
    <>
      <p className="admin-note">
        Showing {page.offset + 1}-{Math.min(page.offset + page.items.length, page.total)} of {page.total} documents
        {sourceName ? ` from ${sourceName}` : ' across all sources'}.
      </p>
      <div className="admin-table-wrap">
        <table className="admin-table">
        <thead>
          <tr>
            <th>Document</th>
            <th>Source</th>
            <th>Type</th>
            <th>Published</th>
          </tr>
        </thead>
        <tbody>
          {documents.map((document) => (
            <tr key={document.id}>
              <td><a href={document.url}>{document.title || document.url}</a></td>
              <td>{document.source_domain}</td>
              <td>{document.document_type}</td>
              <td>{formatDate(document.published_at)}</td>
            </tr>
          ))}
        </tbody>
        </table>
      </div>
    </>
  );
}

function Pagination<T>({ page, onChange }: { page: Page<T>; onChange: (next: PageState) => void }) {
  const start = page.total === 0 ? 0 : page.offset + 1;
  const end = Math.min(page.offset + page.items.length, page.total);

  function setLimit(value: string) {
    onChange({ limit: Number(value), offset: 0 });
  }

  return (
    <div className="pagination">
      <span>{start}-{end} of {page.total}</span>
      <select value={page.limit} onChange={(event) => setLimit(event.target.value)}>
        <option value={25}>25 / page</option>
        <option value={50}>50 / page</option>
        <option value={100}>100 / page</option>
        <option value={250}>250 / page</option>
      </select>
      <button type="button" disabled={!page.has_previous} onClick={() => onChange({ limit: page.limit, offset: Math.max(0, page.offset - page.limit) })}>
        Previous
      </button>
      <button type="button" disabled={!page.has_next} onClick={() => onChange({ limit: page.limit, offset: page.offset + page.limit })}>
        Next
      </button>
    </div>
  );
}

function AdminJobsTable({ jobs }: { jobs: AdminCrawlJob[] }) {
  return (
    <div className="admin-table-wrap">
      <table className="admin-table">
        <thead>
          <tr>
            <th>Job</th>
            <th>Source</th>
            <th>Status</th>
            <th>Why It Stopped</th>
            <th>Fetched</th>
            <th>Docs</th>
            <th>Links</th>
            <th>Discovered</th>
            <th>Started</th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((job) => (
            <tr key={job.id}>
              <td><JobLabel job={job} /></td>
              <td>{job.source_domain}</td>
              <td>
                <StatusPill value={job.status} />
                {job.error && <small>{job.error.split('\n')[0]}</small>}
              </td>
              <td>{job.outcome}</td>
              <td>{job.pages_fetched}</td>
              <td>{job.documents_indexed}</td>
              <td>{job.links_seen}</td>
              <td>{job.sources_discovered}</td>
              <td>{formatDate(job.started_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function JobLabel({ job }: { job: { id: number; index_run_id: number | null; pages_fetched?: number; documents_indexed?: number } }) {
  return (
    <span className="job-label">
      crawl job {job.id}
      {job.index_run_id ? <small>index run {job.index_run_id}</small> : <small>manual crawl</small>}
      {typeof job.pages_fetched === 'number' && typeof job.documents_indexed === 'number' && (
        <small>{job.pages_fetched} pages fetched / {job.documents_indexed} essay docs</small>
      )}
    </span>
  );
}

function AdminRunsTable({ runs }: { runs: AdminIndexRun[] }) {
  return (
    <div className="admin-table-wrap">
      <table className="admin-table">
        <thead>
          <tr>
            <th>Run</th>
            <th>Status</th>
            <th>Plan</th>
            <th>Crawled</th>
            <th>Ignored</th>
            <th>Docs</th>
            <th>Errors</th>
            <th>Stop</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr key={run.id}>
              <td>{run.id}<small>{formatDate(run.started_at)}</small></td>
              <td><StatusPill value={run.status} /></td>
              <td>{run.attempted_sources}/{run.planned_sources}</td>
              <td>{run.crawled_sources}</td>
              <td>{run.ignored_sources}</td>
              <td>{run.documents_indexed}</td>
              <td>{run.errors}</td>
              <td>{run.stop_reason ?? '-'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StatusPill({ value }: { value: string }) {
  return <span className={`status-pill status-${value}`}>{value}</span>;
}

function formatDate(value: string | null | undefined) {
  if (!value) return '-';
  return new Date(value).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
}

export default function App() {
  const [view, setView] = useState<View>('search');
  return (
    <main>
      <header className="app-header">
        <div>
          <h1>iris</h1>
          <p>Agentic search and digest over a self-growing corpus of essays.</p>
        </div>
        <nav>
          <button className={view === 'search' ? 'active' : ''} onClick={() => setView('search')}>
            <Search size={16} /> Search
          </button>
          <button className={view === 'digest' ? 'active' : ''} onClick={() => setView('digest')}>
            <BookOpen size={16} /> Digest
          </button>
          <button className={view === 'sources' ? 'active' : ''} onClick={() => setView('sources')}>
            <Database size={16} /> Sources
          </button>
          <button className={view === 'admin' ? 'active' : ''} onClick={() => setView('admin')}>
            <LayoutDashboard size={16} /> Admin
          </button>
        </nav>
      </header>
      {view === 'search' && <SearchView />}
      {view === 'digest' && <DigestView />}
      {view === 'sources' && <SourcesView />}
      {view === 'admin' && <AdminView />}
    </main>
  );
}
