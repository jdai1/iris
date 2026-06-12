export interface Source {
  id: number;
  canonical_domain: string;
  url: string;
  name: string | null;
  status: string;
  rss_url: string | null;
  first_seen_at: string;
  last_checked_at: string | null;
}

export interface Document {
  id: number;
  source_id: number;
  source_domain: string;
  url: string;
  document_type: string;
  title: string | null;
  author: string | null;
  published_at: string | null;
  summary: string | null;
  topics: string[];
}

export interface SearchResult {
  document: Document;
  score: number;
  reason: string;
}

export interface SearchResponse {
  search_id: number | null;
  query: string;
  answer: string;
  results: SearchResult[];
}

export interface DigestItem {
  id: number;
  document: Document;
  score: number;
  reason: string;
  status: string;
}

export interface AdminOverview {
  totals: Record<string, number>;
  source_statuses: Record<string, number>;
  document_types: Record<string, number>;
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
  has_next: boolean;
  has_previous: boolean;
}

export interface AdminSource {
  id: number;
  canonical_domain: string;
  url: string;
  status: string;
  description: string | null;
  rss_url: string | null;
  sitemap_url: string | null;
  first_seen_at: string;
  last_checked_at: string | null;
  document_count: number;
  essay_count: number;
  latest_job: {
    id: number;
    index_run_id: number | null;
    status: string;
    outcome: string;
    pages_fetched: number;
    pages_failed: number;
    documents_indexed: number;
    links_seen: number;
    sources_discovered: number;
    started_at: string;
    finished_at: string | null;
    error: string | null;
  } | null;
}

export interface AdminCrawlJob {
  id: number;
  source_id: number;
  source_domain: string;
  index_run_id: number | null;
  status: string;
  outcome: string;
  pages_fetched: number;
  pages_failed: number;
  documents_indexed: number;
  links_seen: number;
  sources_discovered: number;
  started_at: string;
  finished_at: string | null;
  error: string | null;
}

export interface AdminIndexRun {
  id: number;
  status: string;
  mode: string;
  dry_run: boolean;
  started_at: string;
  finished_at: string | null;
  budget_sources: number;
  max_pages: number;
  max_depth: number;
  planned_sources: number;
  attempted_sources: number;
  crawled_sources: number;
  ignored_sources: number;
  documents_indexed: number;
  links_seen: number;
  sources_discovered: number;
  errors: number;
  stop_reason: string | null;
}
