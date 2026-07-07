import { FormEvent, useEffect, useRef, useState } from 'react';
import { Flex, Heading, SimpleGrid, Text } from '@chakra-ui/react';
import {
  getAdminCrawlJobs,
  getAdminDocuments,
  getAdminIndexRuns,
  getAdminOverview,
  getAdminSources,
} from '../api';
import { emptyPage } from '../app/paging';
import { Pagination, type PageState } from '../components/Pagination';
import { StatusPill } from '../components/StatusPill';
import { Button, Chip, ChipList, MetricCard, StateMessage } from '../components/ui';
import type { AdminCrawlJob, AdminIndexRun, AdminOverview, AdminSource, Document, Page } from '../types';

export function AdminView() {
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [sourcesPage, setSourcesPage] = useState<Page<AdminSource>>(emptyPage);
  const [documentsPage, setDocumentsPage] = useState<Page<Document>>(emptyPage);
  const [jobsPage, setJobsPage] = useState<Page<AdminCrawlJob>>(emptyPage);
  const [runsPage, setRunsPage] = useState<Page<AdminIndexRun>>(emptyPage);
  const [status, setStatus] = useState('indexed');
  const [query, setQuery] = useState('');
  const [documentSourceId, setDocumentSourceId] = useState<number | undefined>(undefined);
  const [documentType, setDocumentType] = useState('all');
  const [documentCrawlJobId, setDocumentCrawlJobId] = useState<number | undefined>(undefined);
  const [documentIndexRunId, setDocumentIndexRunId] = useState<number | undefined>(undefined);
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
  const refreshId = useRef(0);

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
    nextDocumentCrawlJobId = documentCrawlJobId,
    nextDocumentIndexRunId = documentIndexRunId,
  ) {
    const requestId = refreshId.current + 1;
    refreshId.current = requestId;
    setLoading(true);
    setError(null);
    try {
      const [overviewData, sourceData, documentData, jobData, runData] = await Promise.all([
        getAdminOverview(),
        getAdminSources({ status: nextStatus, q: nextQuery.trim(), ...nextSourcePage }),
        getAdminDocuments({
          ...nextDocumentPage,
          sourceId: nextDocumentSourceId,
          documentType: nextDocumentType,
          crawlJobId: nextDocumentCrawlJobId,
          indexRunId: nextDocumentIndexRunId,
        }),
        getAdminCrawlJobs({ ...nextJobPage, status: nextJobStatus, sourceId: nextJobSourceId, indexRunId: nextJobRunId }),
        getAdminIndexRuns({ ...nextRunPage, status: nextRunStatus }),
      ]);
      if (refreshId.current === requestId) {
        setOverview(overviewData);
        setSourcesPage(sourceData);
        setDocumentsPage(documentData);
        setJobsPage(jobData);
        setRunsPage(runData);
        setError(null);
      }
    } catch (err) {
      if (refreshId.current === requestId) {
        setError(err instanceof Error ? err.message : 'Admin data failed');
      }
    } finally {
      if (refreshId.current === requestId) {
        setLoading(false);
      }
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
    setDocumentCrawlJobId(undefined);
    setDocumentIndexRunId(undefined);
    setDocumentPageState(nextPage);
    refresh(status, query, nextSourceId, documentType, sourcePageState, nextPage, jobPageState, runPageState, jobStatus, jobSourceId, jobRunId, runStatus, undefined, undefined);
  }

  function updateDocumentType(nextType: string) {
    const nextPage = { ...documentPageState, offset: 0 };
    setDocumentType(nextType);
    setDocumentPageState(nextPage);
    refresh(status, query, documentSourceId, nextType, sourcePageState, nextPage, jobPageState, runPageState, jobStatus, jobSourceId, jobRunId, runStatus, documentCrawlJobId, documentIndexRunId);
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

  function showDocumentsForJob(job: AdminCrawlJob) {
    const nextPage = { ...documentPageState, offset: 0 };
    setActiveTable('documents');
    setDocumentSourceId(job.source_id);
    setDocumentCrawlJobId(job.id);
    setDocumentIndexRunId(undefined);
    setDocumentPageState(nextPage);
    refresh(status, query, job.source_id, documentType, sourcePageState, nextPage, jobPageState, runPageState, jobStatus, jobSourceId, jobRunId, runStatus, job.id, undefined);
  }

  function showJobsForRun(run: AdminIndexRun) {
    const nextPage = { ...jobPageState, offset: 0 };
    setActiveTable('jobs');
    setJobRunId(run.id);
    setJobPageState(nextPage);
    refresh(status, query, documentSourceId, documentType, sourcePageState, documentPageState, nextPage, runPageState, jobStatus, jobSourceId, run.id, runStatus);
  }

  function showDocumentsForRun(run: AdminIndexRun) {
    const nextPage = { ...documentPageState, offset: 0 };
    setActiveTable('documents');
    setDocumentSourceId(undefined);
    setDocumentCrawlJobId(undefined);
    setDocumentIndexRunId(run.id);
    setDocumentPageState(nextPage);
    refresh(status, query, undefined, documentType, sourcePageState, nextPage, jobPageState, runPageState, jobStatus, jobSourceId, jobRunId, runStatus, undefined, run.id);
  }

  function clearDocumentScope() {
    const nextPage = { ...documentPageState, offset: 0 };
    setDocumentCrawlJobId(undefined);
    setDocumentIndexRunId(undefined);
    setDocumentPageState(nextPage);
    refresh(status, query, documentSourceId, documentType, sourcePageState, nextPage, jobPageState, runPageState, jobStatus, jobSourceId, jobRunId, runStatus, undefined, undefined);
  }

  const crawledSources = overview?.source_statuses.indexed ?? 0;
  const activeSources = overview?.source_statuses.crawling ?? 0;

  return (
    <section>
      <Flex className="section-header">
        <div>
          <Heading as="h2" fontSize="2xl" fontWeight="600">Admin</Heading>
          <Text color="iris.500" mt="1">Read-only database view for ingestion, crawl runs, sources, and documents.</Text>
        </div>
        <Button type="button" uiVariant="outline" onClick={() => refresh()}>
          Refresh
        </Button>
      </Flex>

      {error && <StateMessage className="error" tone="error">{error}</StateMessage>}

      <SimpleGrid className="metric-grid" columns={{ base: 2, md: 3, xl: 6 }} gap="2.5">
        <MetricCard className="metric" label="sources crawled" value={crawledSources} />
        <MetricCard className="metric" label="active crawls" value={activeSources} />
        <MetricCard className="metric" label="documents" value={overview?.totals.documents ?? 0} />
        <MetricCard className="metric" label="essays" value={overview?.totals.essay_documents ?? 0} />
        <MetricCard className="metric" label="links" value={overview?.totals.links ?? 0} />
        <MetricCard className="metric" label="resolved links" value={overview?.totals.resolved_links ?? 0} />
      </SimpleGrid>

      <div className="admin-controls">
        <div className="tab-strip">
          {(['sources', 'documents', 'jobs', 'runs'] as const).map((table) => (
            <Button
              key={table}
              type="button"
              uiVariant="tab"
              className={activeTable === table ? 'active' : ''}
              onClick={() => setActiveTable(table)}
            >
              {table}
            </Button>
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
            <Button type="submit" uiVariant="outline">Apply</Button>
          </form>
        )}
        {activeTable === 'documents' && (
          <div className="admin-document-controls">
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
            {(documentCrawlJobId || documentIndexRunId) && (
              <div className="admin-scope-banner">
                <span>
                  Showing documents inferred from {documentCrawlJobId ? `crawl job ${documentCrawlJobId}` : `index run ${documentIndexRunId}`}.
                </span>
                <Button type="button" uiVariant="rowAction" onClick={clearDocumentScope}>Clear scope</Button>
              </div>
            )}
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

      {loading ? <StateMessage className="empty-state">Loading admin data...</StateMessage> : null}
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
            crawlJobId={documentCrawlJobId}
            indexRunId={documentIndexRunId}
          />
          <Pagination page={documentsPage} onChange={pageDocuments} />
        </>
      )}
      {!loading && activeTable === 'jobs' && (
        <>
          <Pagination page={jobsPage} onChange={pageJobs} />
          <AdminJobsTable jobs={jobsPage.items} onShowDocuments={showDocumentsForJob} />
          <Pagination page={jobsPage} onChange={pageJobs} />
        </>
      )}
      {!loading && activeTable === 'runs' && (
        <>
          <Pagination page={runsPage} onChange={pageRuns} />
          <AdminRunsTable runs={runsPage.items} onShowJobs={showJobsForRun} onShowDocuments={showDocumentsForRun} />
          <Pagination page={runsPage} onChange={pageRuns} />
        </>
      )}
    </section>
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
            <th>Stored</th>
            <th>Essays</th>
            <th>Latest Crawl</th>
            <th>Why It Stopped</th>
            <th>Checked</th>
          </tr>
        </thead>
        <tbody>
          {sources.map((source) => (
            <tr key={source.id}>
              <td data-label="Domain">
                <a href={source.url} target="_blank" rel="noreferrer">{source.canonical_domain}</a>
                {source.description && <small>{source.description}</small>}
              </td>
              <td data-label="Status"><StatusPill value={source.status} /></td>
              <td data-label="Stored">{source.document_count}</td>
              <td data-label="Essays">{source.essay_count}</td>
              <td data-label="Latest Crawl">{source.latest_job ? <JobLabel job={source.latest_job} /> : 'none'}</td>
              <td data-label="Why It Stopped">{source.latest_job?.outcome ?? '-'}</td>
              <td data-label="Checked">{formatDate(source.last_checked_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {sources.length === 0 && <StateMessage className="empty-state">No sources match this filter.</StateMessage>}
    </div>
  );
}

function AdminDocumentsTable({
  documents,
  page,
  sourceName,
  crawlJobId,
  indexRunId,
}: {
  documents: Document[];
  page: Page<Document>;
  sourceName?: string;
  crawlJobId?: number;
  indexRunId?: number;
}) {
  const scope = crawlJobId ? ` for crawl job ${crawlJobId}` : indexRunId ? ` for index run ${indexRunId}` : '';
  const start = page.total === 0 ? 0 : page.offset + 1;
  const end = Math.min(page.offset + page.items.length, page.total);
  return (
    <>
      <p className="admin-note">
        Showing {start}-{end} of {page.total} documents
        {sourceName ? ` from ${sourceName}` : ' across all sources'}{scope}.
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
              <td data-label="Document">
                <div className="admin-document-cell">
                  <a href={document.url} target="_blank" rel="noreferrer">{document.title || document.url}</a>
                  <small className="admin-document-url">{document.url}</small>
                  {document.summary && <p>{document.summary}</p>}
                  {document.topics.length > 0 && (
                    <ChipList className="admin-document-topics">
                      {document.topics.map((topic) => (
                        <Chip key={topic}>{topic}</Chip>
                      ))}
                    </ChipList>
                  )}
                </div>
              </td>
              <td data-label="Source">{document.source_domain}</td>
              <td data-label="Type">{document.document_type}</td>
              <td data-label="Published">{formatDate(document.published_at)}</td>
            </tr>
          ))}
        </tbody>
        </table>
      </div>
    </>
  );
}

function AdminJobsTable({ jobs, onShowDocuments }: { jobs: AdminCrawlJob[]; onShowDocuments: (job: AdminCrawlJob) => void }) {
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
            <th>Inspect</th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((job) => (
            <tr key={job.id}>
              <td data-label="Job"><JobLabel job={job} /></td>
              <td data-label="Source">{job.source_domain}</td>
              <td data-label="Status">
                <StatusPill value={job.status} />
                {job.error && <small>{job.error.split('\n')[0]}</small>}
              </td>
              <td data-label="Why It Stopped">{job.outcome}</td>
              <td data-label="Fetched">{job.pages_fetched}</td>
              <td data-label="Docs">
                {job.current_document_count}
                <small>{job.documents_indexed} essays accepted</small>
              </td>
              <td data-label="Links">{job.links_seen}</td>
              <td data-label="Discovered">{job.sources_discovered}</td>
              <td data-label="Started">{formatDate(job.started_at)}</td>
              <td data-label="Inspect">
                <Button className="admin-inline-action" uiVariant="rowAction" type="button" onClick={() => onShowDocuments(job)}>
                  View docs
                </Button>
              </td>
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

function AdminRunsTable({
  runs,
  onShowJobs,
  onShowDocuments,
}: {
  runs: AdminIndexRun[];
  onShowJobs: (run: AdminIndexRun) => void;
  onShowDocuments: (run: AdminIndexRun) => void;
}) {
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
            <th>Stored</th>
            <th>Errors</th>
            <th>Stop</th>
            <th>Inspect</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr key={run.id}>
              <td data-label="Run">{run.id}<small>{formatDate(run.started_at)}</small></td>
              <td data-label="Status"><StatusPill value={run.status} /></td>
              <td data-label="Plan">{run.attempted_sources}/{run.planned_sources}</td>
              <td data-label="Crawled">{run.crawled_sources}</td>
              <td data-label="Ignored">{run.ignored_sources}</td>
              <td data-label="Stored">
                {run.current_document_count}
                <small>{run.documents_indexed} essays accepted</small>
              </td>
              <td data-label="Errors">{run.errors}</td>
              <td data-label="Stop">{run.stop_reason ?? '-'}</td>
              <td data-label="Inspect">
                <div className="admin-inline-actions">
                  <Button className="admin-inline-action" uiVariant="rowAction" type="button" onClick={() => onShowJobs(run)}>
                    View jobs
                  </Button>
                  <Button className="admin-inline-action" uiVariant="rowAction" type="button" onClick={() => onShowDocuments(run)}>
                    View docs
                  </Button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function formatDate(value: string | null | undefined) {
  if (!value) return '-';
  return new Date(value).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
}
