import { FormEvent, ReactNode, useEffect, useMemo, useRef, useState } from 'react';
import {
  Badge,
  Box,
  Button,
  Flex,
  Heading,
  HStack,
  Link,
  SimpleGrid,
  Stack,
  Text,
} from '@chakra-ui/react';
import { ArrowUpRight, BookOpen, GitFork, LayoutDashboard, Orbit, Search, Sparkles, Users } from 'lucide-react';
import {
  getAdminCrawlJobs,
  getAdminDocuments,
  getAdminIndexRuns,
  getAdminOverview,
  getAdminSources,
  getDigest,
  getSourceProfileAnalysis,
  searchCorpus,
} from './api';
import { EmbeddingExplorer } from './EmbeddingExplorer';
import { GraphExplorer } from './GraphExplorer';
import { CorpusSearchForm } from './CorpusSearchForm';
import type { AdminCrawlJob, AdminIndexRun, AdminOverview, AdminSource, DigestRecommendation, Page, SearchResponse, Document, SourceProfileAnalysis } from './types';

type View = 'search' | 'digest' | 'directory' | 'explore' | 'graph' | 'admin';
type PageState = { limit: number; offset: number };
type ProfileTarget = { sourceId: number; domain: string } | null;

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
  onOpenProfile,
  compact = false,
}: {
  document: Document;
  reason: string;
  score?: number;
  onOpenProfile?: (sourceId: number, domain: string) => void;
  compact?: boolean;
}) {
  return (
    <Box as="article" className={compact ? 'document-card document-card-compact' : 'document-card'}>
      {!compact && (
        <HStack gap="2" flexWrap="wrap" color="iris.500" fontSize="xs" textTransform="uppercase">
          <button className="profile-link" type="button" onClick={() => onOpenProfile?.(document.source_id, document.source_domain)}>
            {document.source_domain}
          </button>
          <Text as="span">{document.document_type}</Text>
          {typeof score === 'number' && <Text as="span">{score.toFixed(2)}</Text>}
        </HStack>
      )}
      <div className={compact ? 'document-title-row' : undefined}>
        <Heading as="h3" mt="2" mb="3" fontSize="xl" lineHeight="1.2" fontWeight="650">
          {document.title ?? document.url}
        </Heading>
        {compact && (
          <Link href={document.url} className="document-open-icon" color="iris.900" fontWeight="650" textDecoration="none" aria-label="Open document">
            <ArrowUpRight size={16} />
          </Link>
        )}
      </div>
      {document.summary && <Text color="iris.700" lineHeight="1.6" mb="3">{document.summary}</Text>}
      {!compact && <Text color="iris.500" fontSize="sm" lineHeight="1.55" mb="4">{reason}</Text>}
      <HStack className="topics" gap="1.5" flexWrap="wrap" mb="4">
        {document.topics.slice(0, 6).map((topic) => (
          <Badge key={topic} variant="outline" borderColor="iris.300" color="iris.700" bg="iris.100" fontWeight="500">
            {topic}
          </Badge>
        ))}
      </HStack>
      {!compact && (
        <HStack>
          <Link href={document.url} color="iris.900" fontWeight="650" textDecoration="none">
            <ArrowUpRight size={16} />
            Open
          </Link>
        </HStack>
      )}
    </Box>
  );
}

function SearchView({ onOpenProfile }: { onOpenProfile: (sourceId: number, domain: string) => void }) {
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

  return (
    <Box as="section" className="search-view">
      <CorpusSearchForm
        className="search-box"
        value={query}
        onChange={setQuery}
        onSubmit={submit}
        placeholder={loading ? 'Searching...' : 'Ask anything across the corpus...'}
        disabled={loading || !query.trim()}
        autoFocus
      />

      {error && <div className="error">{error}</div>}

      {response && (
        <Box className="results-layout">
          <Box as="aside" className="answer-panel">
            <div className="panel-heading">
              <Sparkles size={18} />
              Synthesis
            </div>
            <p>{response.answer}</p>
            {response.tools.length > 0 && (
              <div className="tool-trace">
                {response.tools.map((tool) => (
                  <div key={tool.tool}>
                    <strong>{tool.tool}</strong>
                    <span>{tool.hits} hits</span>
                    <small>{tool.top_titles.slice(0, 2).join(' · ') || tool.query}</small>
                  </div>
                ))}
              </div>
            )}
          </Box>
          <div className="results-list">
            {response.results.map((result) => (
              <DocumentCard
                key={result.document.id}
                document={result.document}
                reason={result.reason}
                score={result.score}
                onOpenProfile={onOpenProfile}
              />
            ))}
          </div>
        </Box>
      )}
    </Box>
  );
}

function DigestView({ onOpenProfile }: { onOpenProfile: (sourceId: number, domain: string) => void }) {
  const [items, setItems] = useState<DigestRecommendation[]>([]);
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

  if (loading) return <div className="empty-state">Loading digest...</div>;

  return (
    <section>
      <Flex className="section-header">
        <div>
          <Heading as="h2" fontSize="2xl" fontWeight="650">Digest</Heading>
          <Text color="iris.500" mt="1">Old and new corpus items ranked by fit, quality, and graph signal.</Text>
        </div>
        <Button type="button" onClick={refresh} variant="outline" borderRadius="0">Refresh</Button>
      </Flex>
      <Stack gap="3">
        {error && <div className="error">{error}</div>}
        {items.map((item) => (
          <DocumentCard
            key={item.document.id}
            document={item.document}
            reason={item.reason}
            score={item.score}
            onOpenProfile={onOpenProfile}
          />
        ))}
        {items.length === 0 && <div className="empty-state">No digest items yet. Add and crawl a source.</div>}
      </Stack>
    </section>
  );
}

function DirectoryView({ target, onOpenProfile }: { target: ProfileTarget; onOpenProfile: (sourceId: number, domain: string) => void }) {
  const [query, setQuery] = useState(target?.domain ?? '');
  const [selectedSource, setSelectedSource] = useState<AdminSource | null>(null);
  const [suggestions, setSuggestions] = useState<AdminSource[]>([]);
  const [suggestionsOpen, setSuggestionsOpen] = useState(false);
  const [documentsPage, setDocumentsPage] = useState<Page<Document>>(emptyPage);
  const [profileAnalysis, setProfileAnalysis] = useState<SourceProfileAnalysis | null>(null);
  const [selected, setSelected] = useState<ProfileTarget>(target);
  const [documentPageState, setDocumentPageState] = useState<PageState>({ limit: 50, offset: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const suppressSuggestionsRef = useRef(false);

  useEffect(() => {
    setSelected(target);
    if (target) setQuery(target.domain);
  }, [target?.sourceId, target?.domain]);

  async function refresh(nextQuery = query, nextSelected = selected, nextPage = documentPageState) {
    setLoading(true);
    setError(null);
    try {
      const sources = await getAdminSources({ status: 'indexed', q: nextQuery.trim(), limit: 25 });
      const source =
        (nextSelected && sources.items.find((item) => item.id === nextSelected.sourceId)) ??
        sources.items.find((item) => item.canonical_domain === nextQuery.trim().toLowerCase()) ??
        sources.items[0] ??
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
      setLoading(false);
    }
  }

  useEffect(() => {
    const nextPage = { limit: 50, offset: 0 };
    setDocumentPageState(nextPage);
    refresh(target?.domain ?? '', target, nextPage);
  }, [target?.sourceId, target?.domain]);

  useEffect(() => {
    const normalized = query.trim();
    if (suppressSuggestionsRef.current) {
      suppressSuggestionsRef.current = false;
      setSuggestionsOpen(false);
      return;
    }
    if (!normalized) {
      setSuggestions([]);
      setSuggestionsOpen(false);
      return;
    }
    let mounted = true;
    getAdminSources({ status: 'indexed', q: normalized, limit: 8 })
      .then((page) => {
        if (!mounted) return;
        setSuggestions(page.items);
        setSuggestionsOpen(true);
      })
      .catch(() => {
        if (!mounted) return;
        setSuggestions([]);
        setSuggestionsOpen(false);
      });
    return () => {
      mounted = false;
    };
  }, [query]);

  function submit(event: FormEvent) {
    event.preventDefault();
    const nextPage = { limit: documentPageState.limit, offset: 0 };
    setDocumentPageState(nextPage);
    setSuggestionsOpen(false);
    refresh(query, null, nextPage);
  }

  function updateQuery(value: string) {
    setQuery(value);
    setSuggestionsOpen(Boolean(value.trim()));
  }

  function selectSuggestion(source: AdminSource) {
    const nextPage = { limit: documentPageState.limit, offset: 0 };
    const nextProfile = { sourceId: source.id, domain: source.canonical_domain };
    suppressSuggestionsRef.current = true;
    setQuery(source.canonical_domain);
    setSelected(nextProfile);
    setSelectedSource(source);
    setDocumentPageState(nextPage);
    setSuggestionsOpen(false);
    refresh(source.canonical_domain, nextProfile, nextPage);
  }

  function pageProfileDocuments(nextPage: PageState) {
    setDocumentPageState(nextPage);
    refresh(selected?.domain ?? query, selected, nextPage);
  }

  return (
    <Box as="section" className="directory-view">
      <CorpusSearchForm
        className="search-box"
        value={query}
        onChange={updateQuery}
        onSubmit={submit}
        placeholder={loading ? 'Loading profile...' : 'Find a person or domain...'}
        disabled={loading || !query.trim()}
      >
        {suggestionsOpen && suggestions.length > 0 && (
          <div className="directory-suggestions">
            {suggestions.map((source) => (
              <button key={source.id} type="button" onClick={() => selectSuggestion(source)}>
                <span>{source.canonical_domain}</span>
                <small>{source.essay_count} essays</small>
              </button>
            ))}
          </div>
        )}
      </CorpusSearchForm>

      {error && <div className="error">{error}</div>}
      {loading && <div className="empty-state">Loading directory...</div>}

      {!loading && (
        <div className="profile-panel">
            {selected ? (
              <>
                <div className="profile-heading">
                  <div>
                    <h3>{profileAnalysis?.display_name || selectedSource?.canonical_domain || selected.domain}</h3>
                    {profileAnalysis?.display_name && profileAnalysis.display_name !== selected.domain && <p>{selectedSource?.canonical_domain ?? selected.domain}</p>}
                  </div>
                  <a href={selectedSource?.url ?? `https://${selected.domain}`}>
                    <ArrowUpRight size={16} />
                  </a>
                </div>
                <ProfileAnalysisCard analysis={profileAnalysis} />
                <div className="profile-documents">
                  {documentsPage.items.map((document) => (
                    <DocumentCard
                      key={document.id}
                      document={document}
                      reason={document.summary ? 'From this profile.' : 'Indexed essay from this profile.'}
                      onOpenProfile={onOpenProfile}
                      compact
                    />
                  ))}
                </div>
                <ProfilePagination page={documentsPage} onChange={pageProfileDocuments} />
              </>
            ) : (
              <div className="empty-state">Search for an indexed profile.</div>
            )}
          </div>
      )}
    </Box>
  );
}

function ProfilePagination<T>({ page, onChange }: { page: Page<T>; onChange: (next: PageState) => void }) {
  const start = page.total === 0 ? 0 : page.offset + 1;
  const end = Math.min(page.offset + page.items.length, page.total);

  return (
    <div className="profile-pagination">
      <button type="button" disabled={!page.has_previous} onClick={() => onChange({ limit: page.limit, offset: Math.max(0, page.offset - page.limit) })} aria-label="Previous profile documents">
        ←
      </button>
      <span>{start}-{end} of {page.total}</span>
      <button type="button" disabled={!page.has_next} onClick={() => onChange({ limit: page.limit, offset: page.offset + page.limit })} aria-label="Next profile documents">
        →
      </button>
    </div>
  );
}

function ProfileAnalysisCard({ analysis }: { analysis: SourceProfileAnalysis | null }) {
  const payload = analysis?.payload;
  const facts = analysis?.scraped_facts;
  const themes = payload?.themes?.length ? payload.themes : facts?.top_topics?.slice(0, 12).map((item) => item.topic) ?? [];
  const links = payload?.public_links?.length ? payload.public_links : facts?.public_links ?? [];
  const contact = payload?.public_contact?.length ? payload.public_contact : facts?.public_contact ?? [];
  const unavailable = new Set(analysis?.unavailable_sections ?? payload?.unavailable_sections ?? []);

  if (!analysis) {
    return (
      <div className="profile-analysis-card">
        <ProfileUnavailable labels={['bio', 'themes', 'writing style', 'strong takes', 'links', 'contact']} />
      </div>
    );
  }

  return (
    <div className="profile-analysis-card">
      {payload?.bio ? <p className="profile-bio">{payload.bio}</p> : <ProfileUnavailable labels={['bio']} />}
      <ProfileChipSection title="Writes about" items={themes} unavailable={unavailable.has('themes')} />
      <ProfileChipSection title="Style" items={payload?.writing_style ?? []} unavailable={unavailable.has('writing_style')} />
      <ProfileTakeSection takes={payload?.strong_takes ?? []} unavailable={unavailable.has('strong_takes')} />
      <ProfileLinkSection title="Links" links={links} unavailable={unavailable.has('public_links')} />
      <ProfileLinkSection title="Contact" links={contact} unavailable={unavailable.has('public_contact')} />
      {payload?.caveats && payload.caveats.length > 0 && (
        <div className="profile-caveats">
          {payload.caveats.map((caveat) => <span key={caveat}>{caveat}</span>)}
        </div>
      )}
    </div>
  );
}

function ProfileChipSection({ title, items, unavailable }: { title: string; items: string[]; unavailable: boolean }) {
  if (!items.length) return unavailable ? <ProfileUnavailable labels={[title.toLowerCase()]} /> : null;
  return (
    <div className="profile-analysis-section">
      <h4>{title}</h4>
      <div className="profile-chip-list">
        {items.map((item) => <span key={item}>{item}</span>)}
      </div>
    </div>
  );
}

function ProfileTakeSection({ takes, unavailable }: { takes: Array<{ take: string; evidence_document_ids: number[] }>; unavailable: boolean }) {
  if (!takes.length) return unavailable ? <ProfileUnavailable labels={['strong takes']} /> : null;
  return (
    <div className="profile-analysis-section">
      <h4>Strong takes</h4>
      <ul className="profile-take-list">
        {takes.map((item) => <li key={item.take}>{item.take}</li>)}
      </ul>
    </div>
  );
}

function ProfileLinkSection({ title, links, unavailable }: { title: string; links: Array<{ label?: string; url?: string; kind?: string }>; unavailable: boolean }) {
  const usable = links.filter((link) => link.url);
  if (!usable.length) return unavailable ? <ProfileUnavailable labels={[title.toLowerCase()]} /> : null;
  return (
    <div className="profile-analysis-section">
      <h4>{title}</h4>
      <div className="profile-link-list">
        {usable.map((link) => (
          <a key={link.url} href={link.url}>
            {link.label || link.kind || link.url}
          </a>
        ))}
      </div>
    </div>
  );
}

function ProfileUnavailable({ labels }: { labels: string[] }) {
  return (
    <div className="profile-unavailable">
      {labels.map((label) => <span key={label}>{label} unavailable</span>)}
    </div>
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
          <Heading as="h2" fontSize="2xl" fontWeight="650">Admin</Heading>
          <Text color="iris.500" mt="1">Read-only database view for ingestion, crawl runs, sources, and documents.</Text>
        </div>
        <Button type="button" onClick={() => refresh()} variant="outline" borderRadius="0">
          Refresh
        </Button>
      </Flex>

      {error && <div className="error">{error}</div>}

      <SimpleGrid className="metric-grid" columns={{ base: 2, md: 3, xl: 6 }} gap="2.5">
        <Metric label="sources crawled" value={crawledSources} />
        <Metric label="active crawls" value={activeSources} />
        <Metric label="documents" value={overview?.totals.documents ?? 0} />
        <Metric label="essays" value={overview?.totals.essay_documents ?? 0} />
        <Metric label="links" value={overview?.totals.links ?? 0} />
        <Metric label="resolved links" value={overview?.totals.resolved_links ?? 0} />
      </SimpleGrid>

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
                <button type="button" onClick={clearDocumentScope}>Clear scope</button>
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

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <Box className="metric">
      <Text as="span">{label}</Text>
      <Text as="strong">{value.toLocaleString()}</Text>
    </Box>
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
              <td>
                <div className="admin-document-cell">
                  <a href={document.url}>{document.title || document.url}</a>
                  <small className="admin-document-url">{document.url}</small>
                  {document.summary && <p>{document.summary}</p>}
                  {document.topics.length > 0 && (
                    <div className="admin-document-topics">
                      {document.topics.slice(0, 8).map((topic) => (
                        <span key={topic}>{topic}</span>
                      ))}
                    </div>
                  )}
                </div>
              </td>
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
              <td><JobLabel job={job} /></td>
              <td>{job.source_domain}</td>
              <td>
                <StatusPill value={job.status} />
                {job.error && <small>{job.error.split('\n')[0]}</small>}
              </td>
              <td>{job.outcome}</td>
              <td>{job.pages_fetched}</td>
              <td>
                {job.current_document_count}
                <small>{job.documents_indexed} essays accepted</small>
              </td>
              <td>{job.links_seen}</td>
              <td>{job.sources_discovered}</td>
              <td>{formatDate(job.started_at)}</td>
              <td>
                <button className="admin-inline-action" type="button" onClick={() => onShowDocuments(job)}>
                  View docs
                </button>
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
              <td>{run.id}<small>{formatDate(run.started_at)}</small></td>
              <td><StatusPill value={run.status} /></td>
              <td>{run.attempted_sources}/{run.planned_sources}</td>
              <td>{run.crawled_sources}</td>
              <td>{run.ignored_sources}</td>
              <td>
                {run.current_document_count}
                <small>{run.documents_indexed} essays accepted</small>
              </td>
              <td>{run.errors}</td>
              <td>{run.stop_reason ?? '-'}</td>
              <td>
                <div className="admin-inline-actions">
                  <button className="admin-inline-action" type="button" onClick={() => onShowJobs(run)}>
                    View jobs
                  </button>
                  <button className="admin-inline-action" type="button" onClick={() => onShowDocuments(run)}>
                    View docs
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StatusPill({ value }: { value: string }) {
  return <Badge className={`status-pill status-${value}`} variant="outline" borderRadius="0">{value}</Badge>;
}

function formatDate(value: string | null | undefined) {
  if (!value) return '-';
  return new Date(value).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
}

export default function App() {
  const [view, setView] = useState<View>('search');
  const [profileTarget, setProfileTarget] = useState<ProfileTarget>(null);

  function openProfile(sourceId: number, domain: string) {
    setProfileTarget({ sourceId, domain });
    setView('directory');
  }

  const navItems: Array<{ view: View; label: string; icon: ReactNode }> = [
    { view: 'search', label: 'Search', icon: <Search size={15} /> },
    { view: 'digest', label: 'Digest', icon: <BookOpen size={15} /> },
    { view: 'explore', label: 'Explore', icon: <Orbit size={15} /> },
    { view: 'graph', label: 'Graph', icon: <GitFork size={15} /> },
    { view: 'directory', label: 'Directory', icon: <Users size={15} /> },
    { view: 'admin', label: 'Admin', icon: <LayoutDashboard size={15} /> },
  ];

  return (
    <Box as="main" className="app-shell">
      <Box as="aside" className="sidebar">
        <Box className="sidebar-brand">
          <span>iris</span>
        </Box>
        <Stack as="nav" className="sidebar-nav" gap="1">
          {navItems.map((item) => (
            <Button
              key={item.view}
              type="button"
              onClick={() => setView(item.view)}
              variant="ghost"
              borderRadius="0"
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
      </Box>
      <Box className={view === 'explore' || view === 'graph' ? 'workspace workspace-fullscreen' : 'workspace'}>
        {view === 'search' && <SearchView onOpenProfile={openProfile} />}
        {view === 'digest' && <DigestView onOpenProfile={openProfile} />}
        {view === 'directory' && <DirectoryView target={profileTarget} onOpenProfile={openProfile} />}
        {view === 'explore' && <EmbeddingExplorer />}
        {view === 'graph' && <GraphExplorer onOpenProfile={openProfile} />}
        {view === 'admin' && <AdminView />}
      </Box>
    </Box>
  );
}
