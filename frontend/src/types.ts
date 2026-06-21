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

export interface User {
  id: number;
  slug: string;
  firebase_uid: string | null;
  email: string | null;
  display_name: string | null;
  photo_url: string | null;
}

export interface Document {
  id: number;
  source_id: number;
  source_domain: string;
  url: string;
  document_type: string;
  category: string;
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

export interface AgentStep {
  kind: string;
  title: string;
  detail: string;
  tool: string | null;
  query: string | null;
  hits: number | null;
}

export interface AgentChatResponse {
  conversation_id: number;
  user_message_id: number;
  assistant_message_id: number;
  message: string;
  answer: string;
  results: SearchResult[];
  steps: AgentStep[];
}

export type AgentStreamEvent =
  | {
      event: 'conversation';
      data: {
        conversation_id: number;
        user_message_id: number;
        message: string;
      };
    }
  | {
      event: 'step';
      data: {
        step: AgentStep;
      };
    }
  | {
      event: 'tool_result';
      data: {
        step: AgentStep;
        hits: Array<{
          document_id: number;
          title: string;
          source_domain: string;
          score: number;
          reason: string;
        }>;
      };
    }
  | {
      event: 'final';
      data: AgentChatResponse;
    }
  | {
      event: 'done';
      data: {
        conversation_id: number;
      };
    }
  | {
      event: 'error';
      data: {
        message: string;
        type: string;
      };
    };

export interface AgentConversationSummary {
  id: number;
  title: string | null;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface AgentMessage {
  id: number;
  role: string;
  content: string;
  created_at: string;
  steps: AgentStep[];
  results: SearchResult[];
}

export interface AgentConversation {
  id: number;
  title: string | null;
  created_at: string;
  updated_at: string;
  messages: AgentMessage[];
}

export interface DigestRecommendation {
  document: Document;
  score: number;
  reason: string;
}

export interface EmbeddingMapPoint {
  document: Document;
  x: number;
  y: number;
  z: number;
  cluster_id: number | null;
}

export interface EmbeddingMap {
  points: EmbeddingMapPoint[];
  total_embedded: number;
  dimensions: number;
  projection_method: string;
}

export interface EmbeddingNeighbor {
  document: Document;
  similarity: number;
}

export interface GraphNode {
  id: string;
  label: string;
  type: string;
  domain: string;
  url: string | null;
  subtitle: string | null;
  summary: string | null;
  size: number;
}

export interface GraphEdge {
  source: string;
  target: string;
  label: string | null;
  weight: number;
}

export interface GraphResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export type SourceProfileAnalysisStatus = 'pending' | 'succeeded' | 'failed';
export type SourceProfileLinkKind = 'homepage' | 'profile' | 'visible_link' | 'email';
export type SourceProfileLink = { label: string; url: string; kind: SourceProfileLinkKind };

export interface SourceProfileAnalysis {
  id: number;
  source_id: number;
  source_domain: string;
  status: SourceProfileAnalysisStatus;
  display_name: string | null;
  generated_at: string | null;
  model: string | null;
  input_fingerprint: string | null;
  bio: string | null;
  themes: string[] | null;
  writing_style: string[] | null;
  strong_takes: Array<{ take: string }> | null;
  public_links: SourceProfileLink[] | null;
  public_contact: SourceProfileLink[] | null;
  caveats: string[] | null;
  scraped_facts: {
    top_topics?: Array<{ topic: string; count: number }>;
    public_links?: SourceProfileLink[];
    public_contact?: SourceProfileLink[];
    profile_pages?: Array<{ id: number; title: string | null; url: string; summary: string | null }>;
    document_counts?: Record<string, number>;
  } | null;
  error: string | null;
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
  current_document_count: number;
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
  current_document_count: number;
  links_seen: number;
  sources_discovered: number;
  errors: number;
  stop_reason: string | null;
}
