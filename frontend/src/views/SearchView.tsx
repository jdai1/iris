import { FormEvent, ReactNode, useEffect, useRef, useState } from 'react';
import { ArrowUpRight, BrainCircuit, ChevronDown, FileSearch, Hash, Search, Tags } from 'lucide-react';
import { getAgentConversation, getAgentConversations, streamChatSearch } from '../api';
import { CorpusSearchForm } from '../CorpusSearchForm';
import { DocumentActionsMenu } from '../components/DocumentActionsMenu';
import { ResizableSidebarLayout } from '../components/ResizableSidebarLayout';
import type { AgentConversation, AgentConversationSummary, AgentInspectedDocument, AgentStep, BookshelfEntry, SearchResult } from '../types';

type ChatMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  results?: SearchResult[];
  steps?: AgentStep[];
  pending?: boolean;
};

type ConversationTurn = {
  id: string;
  query: string;
  response: string;
};

const ACTIVE_CHAT_STORAGE_KEY = 'iris.activeChatUuid';
const SEARCH_RELOAD_STORAGE_KEY = 'iris.searchReloading';
const HISTORY_PAGE_SIZE = 15;

export function SearchView({
  selectedDocumentUuid,
  onOpenDocument,
  artifactOpen = false,
  greetingName,
}: {
  selectedDocumentUuid: string | null;
  onOpenDocument: (documentUuid: string, reason: string) => void;
  artifactOpen?: boolean;
  greetingName?: string | null;
}) {
  const [query, setQuery] = useState('');
  const [conversationId, setConversationId] = useState<string | undefined>();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [history, setHistory] = useState<AgentConversationSummary[]>([]);
  const [historyQuery, setHistoryQuery] = useState('');
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyLoadingMore, setHistoryLoadingMore] = useState(false);
  const [historyHasMore, setHistoryHasMore] = useState(false);
  const [startedNewChat, setStartedNewChat] = useState(false);
  const [activeChatKey, setActiveChatKey] = useState('new:initial');
  const [inFlightChatKeys, setInFlightChatKeys] = useState<Set<string>>(() => new Set());
  const [error, setError] = useState<string | null>(null);
  const [activeTurnId, setActiveTurnId] = useState<string | null>(null);
  const transcriptRef = useRef<HTMLDivElement | null>(null);
  const turnRefs = useRef(new Map<string, HTMLDivElement>());
  const historyRef = useRef<HTMLDivElement | null>(null);
  const activeChatKeyRef = useRef(activeChatKey);
  const newChatSequence = useRef(0);
  const conversationLoadSequence = useRef(0);
  const didLoadInitialConversation = useRef(false);
  const shouldRestoreConversation = useRef(
    typeof window !== 'undefined' && window.sessionStorage.getItem(SEARCH_RELOAD_STORAGE_KEY) === '1',
  );
  const loading = inFlightChatKeys.has(activeChatKey);

  function activateChat(key: string) {
    activeChatKeyRef.current = key;
    setActiveChatKey(key);
  }

  useEffect(() => {
    if (typeof window !== 'undefined') {
      window.sessionStorage.removeItem(SEARCH_RELOAD_STORAGE_KEY);
    }
    loadInitialHistory();
    return () => {
      if (typeof window === 'undefined') return;
      if (window.sessionStorage.getItem(SEARCH_RELOAD_STORAGE_KEY) === '1') return;
      window.sessionStorage.removeItem(ACTIVE_CHAT_STORAGE_KEY);
    };
  }, []);

  useEffect(() => {
    function preserveChatForReload() {
      window.sessionStorage.setItem(SEARCH_RELOAD_STORAGE_KEY, '1');
    }
    window.addEventListener('beforeunload', preserveChatForReload);
    return () => window.removeEventListener('beforeunload', preserveChatForReload);
  }, []);

  useEffect(() => {
    if (conversationId) {
      window.sessionStorage.setItem(ACTIVE_CHAT_STORAGE_KEY, String(conversationId));
    } else {
      window.sessionStorage.removeItem(ACTIVE_CHAT_STORAGE_KEY);
    }
  }, [conversationId]);

  useEffect(() => {
    transcriptRef.current?.scrollTo({ top: transcriptRef.current.scrollHeight, behavior: 'smooth' });
    const latestTurn = [...messages].reverse().find((message) => message.role === 'user');
    if (latestTurn) setActiveTurnId(latestTurn.id);
  }, [messages]);

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      refreshHistory(historyQuery);
    }, 160);
    return () => window.clearTimeout(timeout);
  }, [historyQuery]);

  function openResultDrawer(result: SearchResult) {
    onOpenDocument(result.document.uuid, naturalRelevance(result));
  }

  function updateResultBookshelf(entry: BookshelfEntry) {
    setMessages((current) => current.map((message) => ({
      ...message,
      results: message.results?.map((result) => result.document.uuid === entry.document.uuid
        ? {
            ...result,
            document: {
              ...result.document,
              bookshelf_status: entry.status,
              bookshelf_favorited: entry.favorited,
            },
          }
        : result),
    })));
  }

  async function refreshHistory(nextQuery = historyQuery) {
    setHistoryLoading(true);
    try {
      const items = await getAgentConversations({ limit: HISTORY_PAGE_SIZE, q: nextQuery });
      setHistory(items);
      setHistoryHasMore(items.length === HISTORY_PAGE_SIZE);
    } catch {
      // History is secondary; leave the chat surface usable if it fails.
    } finally {
      setHistoryLoading(false);
    }
  }

  async function loadMoreHistory() {
    if (historyLoadingMore || historyLoading) return;
    setHistoryLoadingMore(true);
    try {
      const items = await getAgentConversations({ limit: HISTORY_PAGE_SIZE, offset: history.length, q: historyQuery });
      setHistory((current) => [...current, ...items]);
      setHistoryHasMore(items.length === HISTORY_PAGE_SIZE);
    } catch {
      // History is secondary; keep the current list intact.
    } finally {
      setHistoryLoadingMore(false);
    }
  }

  async function loadInitialHistory() {
    if (didLoadInitialConversation.current) return;
    didLoadInitialConversation.current = true;
    setHistoryLoading(true);
    try {
      const items = await getAgentConversations({ limit: HISTORY_PAGE_SIZE });
      setHistory(items);
      setHistoryHasMore(items.length === HISTORY_PAGE_SIZE);
      const activeChatId = window.sessionStorage.getItem(ACTIVE_CHAT_STORAGE_KEY);
      if (shouldRestoreConversation.current && activeChatId) {
        await loadConversation(activeChatId);
      }
    } catch {
      // History is secondary; start on a clean chat if it fails.
    } finally {
      setHistoryLoading(false);
    }
  }

  async function loadConversation(id: string) {
    const chatKey = `conversation:${id}`;
    const requestSequence = ++conversationLoadSequence.current;
    activateChat(chatKey);
    setError(null);
    try {
      const conversation = await getAgentConversation(id);
      if (requestSequence !== conversationLoadSequence.current || activeChatKeyRef.current !== chatKey) return;
      setConversationId(conversation.uuid);
      setStartedNewChat(false);
      setMessages(messagesFromConversation(conversation));
    } catch (err) {
      if (requestSequence !== conversationLoadSequence.current || activeChatKeyRef.current !== chatKey) return;
      setError(err instanceof Error ? err.message : 'Could not load chat');
    }
  }

  function startNewChat() {
    conversationLoadSequence.current += 1;
    newChatSequence.current += 1;
    activateChat(`new:${newChatSequence.current}`);
    setStartedNewChat(true);
    setConversationId(undefined);
    setMessages([]);
    setError(null);
  }

  function handleHistoryScroll() {
    const node = historyRef.current;
    if (!node || !historyHasMore || historyLoading || historyLoadingMore) return;
    if (node.scrollTop + node.clientHeight >= node.scrollHeight - 80) {
      loadMoreHistory();
    }
  }

  function handleTranscriptScroll() {
    const transcript = transcriptRef.current;
    if (!transcript) return;
    const anchor = transcript.getBoundingClientRect().top + Math.min(160, transcript.clientHeight * 0.3);
    let nextActive = conversationTurns(messages)[0]?.id ?? null;
    for (const turn of conversationTurns(messages)) {
      const element = turnRefs.current.get(turn.id);
      if (!element || element.getBoundingClientRect().top > anchor) break;
      nextActive = turn.id;
    }
    setActiveTurnId(nextActive);
  }

  function jumpToTurn(turnId: string) {
    const transcript = transcriptRef.current;
    const turn = turnRefs.current.get(turnId);
    if (!transcript || !turn) return;
    const top = turn.getBoundingClientRect().top - transcript.getBoundingClientRect().top + transcript.scrollTop - 24;
    setActiveTurnId(turnId);
    transcript.scrollTo({ top, behavior: 'smooth' });
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const message = query.trim();
    if (!message || loading) return;
    const turnId = Date.now().toString();
    const assistantId = `assistant-${turnId}`;
    let streamKey = activeChatKeyRef.current;
    let streamConversationId = conversationId;
    setMessages((current) => [
      ...current,
      { id: `user-${turnId}`, role: 'user', content: message },
      { id: assistantId, role: 'assistant', content: '', steps: [], pending: true },
    ]);
    setQuery('');
    setInFlightChatKeys((current) => new Set(current).add(streamKey));
    setError(null);
    try {
      await streamChatSearch(message, conversationId, (event) => {
        if (event.event === 'conversation') {
          const nextStreamKey = `conversation:${event.data.conversation_uuid}`;
          const streamIsVisible = activeChatKeyRef.current === streamKey;
          streamConversationId = event.data.conversation_uuid;
          if (nextStreamKey !== streamKey) {
            const previousStreamKey = streamKey;
            streamKey = nextStreamKey;
            setInFlightChatKeys((current) => {
              const next = new Set(current);
              next.delete(previousStreamKey);
              next.add(nextStreamKey);
              return next;
            });
          }
          if (streamIsVisible) {
            activateChat(nextStreamKey);
            setConversationId(event.data.conversation_uuid);
          }
          return;
        }
        if (event.event === 'step') {
          if (activeChatKeyRef.current !== streamKey) return;
          appendAssistantStep(assistantId, event.data.step);
          return;
        }
        if (event.event === 'tool_result') {
          if (activeChatKeyRef.current !== streamKey) return;
          replaceOrAppendAssistantStep(assistantId, {
            ...event.data.step,
            documents: event.data.step.documents?.length
              ? event.data.step.documents
              : event.data.hits,
          });
          return;
        }
        if (event.event === 'final') {
          if (activeChatKeyRef.current === streamKey) {
            setMessages((current) =>
              current.map((item) =>
                item.id === assistantId
                  ? {
                      ...item,
                      content: event.data.answer,
                      results: event.data.results,
                      pending: false,
                    }
                  : item,
              ),
            );
            void getAgentConversation(event.data.conversation_uuid).then((conversation) => {
              if (activeChatKeyRef.current !== streamKey) return;
              setConversationId(conversation.uuid);
              setMessages(messagesFromConversation(conversation));
            });
          }
          refreshHistory();
        }
        if (event.event === 'error') {
          throw new Error(event.data.message);
        }
      });
    } catch (err) {
      if (activeChatKeyRef.current === streamKey) {
        setError(err instanceof Error ? err.message : 'Search failed');
        setMessages((current) =>
          current.map((item) =>
            item.id === assistantId ? { ...item, content: 'Search failed before the agent could finish.', pending: false } : item,
          ),
        );
      }
    } finally {
      setInFlightChatKeys((current) => {
        const next = new Set(current);
        next.delete(streamKey);
        return next;
      });
      if (streamConversationId && activeChatKeyRef.current === streamKey) {
        setConversationId(streamConversationId);
      }
    }
  }

  function appendAssistantStep(assistantId: string, step: AgentStep) {
    if (isSyntheticStep(step)) return;
    setMessages((current) =>
      current.map((item) =>
        item.id === assistantId ? { ...item, steps: [...(item.steps ?? []), step] } : item,
      ),
    );
  }

  function replaceOrAppendAssistantStep(assistantId: string, step: AgentStep) {
    if (isSyntheticStep(step)) return;
    setMessages((current) =>
      current.map((item) => {
        if (item.id !== assistantId) return item;
        const steps = item.steps ?? [];
        const last = steps[steps.length - 1];
        if (last?.kind === 'tool' && last.tool === step.tool && last.hits === null) {
          return { ...item, steps: [...steps.slice(0, -1), step] };
        }
        return { ...item, steps: [...steps, step] };
      }),
    );
  }

  return (
    <section className="min-h-svh flex-1">
      <ResizableSidebarLayout
        className="min-h-svh"
        storageKey="iris.chatHistoryWidth"
        sidebar={<aside className="hidden min-h-svh border-r bg-muted/20 lg:flex lg:flex-col">
          <div className="flex h-14 items-center justify-between px-4 text-sm font-semibold">
            <span>Chats</span>
            <button className="grid size-8 place-items-center rounded-md text-lg text-muted-foreground hover:bg-accent hover:text-accent-foreground" type="button" onClick={startNewChat} aria-label="New chat" title="New chat">
              +
            </button>
          </div>
          <form className="mx-3 flex h-9 items-center gap-2 rounded-md border bg-background px-3 focus-within:ring-2 focus-within:ring-ring/20" onSubmit={(event) => event.preventDefault()}>
            <Search className="size-3.5 text-muted-foreground" />
            <input
              className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
              value={historyQuery}
              onChange={(event) => setHistoryQuery(event.target.value)}
              placeholder="Search chats"
            />
          </form>
          <div className="mt-3 min-h-0 flex-1 space-y-1 overflow-y-auto px-2 pb-3" ref={historyRef} onScroll={handleHistoryScroll}>
            {historyLoading && <HistorySkeleton />}
            {!historyLoading && history.length === 0 && <div className="px-2 py-6 text-center text-xs text-muted-foreground">No saved chats yet.</div>}
            {!historyLoading &&
              history.map((item) => (
                <button
                  key={item.uuid}
                  className={`block w-full truncate rounded-md px-2 py-2 text-left text-sm transition-colors ${
                    item.uuid === conversationId
                      ? 'bg-accent text-accent-foreground'
                      : 'text-muted-foreground hover:bg-accent/70 hover:text-accent-foreground'
                  }`}
                  type="button"
                  onClick={() => loadConversation(item.uuid)}
                >
                  <span>{item.title || 'Untitled search'}</span>
                </button>
              ))}
            {!historyLoading && historyLoadingMore && <HistorySkeleton rows={2} />}
          </div>
        </aside>}
      >

        <div className="relative flex min-h-svh min-w-0 flex-col">

      {error && <div className="mx-auto mt-4 w-full max-w-3xl rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">{error}</div>}

      {messages.length === 0 && (
        <div className="mx-auto grid min-h-svh w-full max-w-3xl place-items-center px-6">
          <div className="relative w-full">
            <h1 className="absolute inset-x-0 bottom-full mb-5 text-center text-2xl font-medium tracking-tight">
              {greetingName ? `Hey, ${greetingName}. What are you curious about?` : 'What are you curious about?'}
            </h1>
            <CorpusSearchForm
              className="w-full"
              value={query}
              onChange={setQuery}
              onSubmit={submit}
              placeholder={loading ? 'Iris is working...' : 'Message Iris...'}
              disabled={loading || !query.trim()}
              autoFocus
              multiline
            />
          </div>
        </div>
      )}

      {messages.length > 0 && (
        <div className="flex min-h-svh min-w-0 flex-1 flex-col">
        <div className="min-h-0 flex-1">
          <div className="relative h-[calc(100svh-6rem)] w-full">
            <div className="pointer-events-none absolute inset-y-0 left-0 z-30">
              <ConversationMinimap
                turns={artifactOpen ? [] : conversationTurns(messages)}
                activeTurnId={activeTurnId}
                onSelect={jumpToTurn}
              />
            </div>
            <div className="h-full w-full overflow-y-auto" ref={transcriptRef} onScroll={handleTranscriptScroll}>
              <div className="mx-auto w-full max-w-3xl space-y-8 px-6 py-10">
                {messages.map((message) => (
                  <div
                    key={message.id}
                    ref={(element) => {
                      if (message.role !== 'user') return;
                      if (element) turnRefs.current.set(message.id, element);
                      else turnRefs.current.delete(message.id);
                    }}
                    className={`grid gap-2 ${
                      message.role === 'user'
                        ? 'ml-auto max-w-[85%] rounded-xl bg-muted px-4 py-3'
                        : 'w-full'
                    }`}
                  >
                    <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{message.role === 'user' ? 'You' : 'Iris'}</div>
                    {message.pending && !message.content ? (
                      <ThinkingState />
                    ) : (
                      <MessageContent content={message.content} />
                    )}
                    {message.steps && message.steps.length > 0 && (
                      <SearchTrace
                        steps={message.steps}
                        onOpenDocument={(document) =>
                          onOpenDocument(document.uuid, traceDocumentReason(document))
                        }
                      />
                    )}
                    {message.role === 'assistant' && message.results && message.results.length > 0 && (
                      <SearchResultsTable
                        results={message.results}
                        selectedDocumentUuid={selectedDocumentUuid}
                        onOpenResult={openResultDrawer}
                        onBookshelfChange={updateResultBookshelf}
                      />
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
        {messages.length > 0 && (
          <div className="sticky bottom-0 border-t bg-background/90 px-6 py-4 backdrop-blur">
            <CorpusSearchForm
              className="mx-auto w-full max-w-3xl"
              value={query}
              onChange={setQuery}
              onSubmit={submit}
              placeholder={loading ? 'Iris is working...' : conversationId ? 'Follow up...' : 'Message Iris...'}
              disabled={loading || !query.trim()}
              autoFocus
              multiline
            />
          </div>
        )}
        </div>
      )}
        </div>
      </ResizableSidebarLayout>
    </section>
  );
}

function ConversationMinimap({
  turns,
  activeTurnId,
  onSelect,
}: {
  turns: ConversationTurn[];
  activeTurnId: string | null;
  onSelect: (turnId: string) => void;
}) {
  if (turns.length < 3) return null;

  return (
    <nav
      className="pointer-events-auto absolute top-1/2 left-3 z-30 hidden max-h-[58vh] -translate-y-1/2 overflow-visible xl:block"
      aria-label="Conversation turns"
    >
      <ol className="grid gap-0.5 py-1.5">
        {turns.map((turn, index) => {
          const active = turn.id === activeTurnId;
          return (
            <li className="group/turn relative flex h-2 items-center" key={turn.id}>
              <button
                className="flex h-3.5 w-7 origin-left items-center transition-transform duration-200 ease-out group-hover/turn:translate-x-0.5 group-focus-within/turn:translate-x-0.5 motion-reduce:transition-none focus-visible:outline-none"
                type="button"
                onClick={() => onSelect(turn.id)}
                aria-current={active ? 'step' : undefined}
                aria-label={`Jump to query ${index + 1}: ${turn.query}`}
              >
                <span
                  className={`h-0.5 origin-left rounded-full transition-[width,background-color,opacity] duration-200 ease-out group-hover/turn:w-6 group-hover/turn:bg-foreground/80 group-hover/turn:opacity-100 group-focus-within/turn:w-6 group-focus-within/turn:bg-foreground/80 group-focus-within/turn:opacity-100 motion-reduce:transition-none ${
                    active ? 'w-4 bg-foreground/80 opacity-100' : 'w-2 bg-muted-foreground/45 opacity-70'
                  }`}
                  aria-hidden="true"
                />
                <span className="pointer-events-none invisible absolute top-1/2 left-8 w-72 origin-left -translate-y-1/2 translate-x-1 scale-95 rounded-lg border bg-popover p-2.5 text-left text-xs text-popover-foreground opacity-0 shadow-lg transition-[opacity,transform,visibility] duration-200 ease-out group-hover/turn:visible group-hover/turn:translate-x-0 group-hover/turn:scale-100 group-hover/turn:opacity-100 group-focus-within/turn:visible group-focus-within/turn:translate-x-0 group-focus-within/turn:scale-100 group-focus-within/turn:opacity-100 motion-reduce:transition-none">
                  <span className="block max-h-24 overflow-y-auto whitespace-pre-wrap font-medium leading-4">
                    {turn.query}
                  </span>
                  {turn.response && (
                    <span className="mt-2 line-clamp-2 block text-muted-foreground">
                      {turn.response}
                    </span>
                  )}
                </span>
              </button>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

function ThinkingState() {
  return (
    <div className="grid gap-3 text-sm text-muted-foreground" aria-live="polite">
      <div className="flex items-center gap-2">
        <span>Thinking</span>
        <span className="animate-pulse" aria-hidden="true">
          through the corpus…
        </span>
      </div>
      <div className="grid gap-2" aria-hidden="true">
        <span className="h-3 w-full animate-pulse rounded bg-muted" />
        <span className="h-3 w-5/6 animate-pulse rounded bg-muted" />
        <span className="h-3 w-2/3 animate-pulse rounded bg-muted" />
      </div>
    </div>
  );
}

function HistorySkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="grid gap-2 px-2 py-1" aria-label="Loading chats">
      {Array.from({ length: rows }).map((_, index) => (
        <span className="h-8 animate-pulse rounded-md bg-muted" key={index} />
      ))}
    </div>
  );
}

function ResultSkeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div className="grid gap-2" aria-label="Loading search results">
      {Array.from({ length: rows }).map((_, index) => (
        <div className="grid gap-2 rounded-lg border p-4" key={index}>
          <span className="h-3 w-1/2 animate-pulse rounded bg-muted" />
          <span className="h-3 w-full animate-pulse rounded bg-muted" />
          <span className="h-3 w-2/3 animate-pulse rounded bg-muted" />
        </div>
      ))}
    </div>
  );
}

function SearchResultsTable({
  results,
  selectedDocumentUuid,
  onOpenResult,
  onBookshelfChange,
}: {
  results: SearchResult[];
  selectedDocumentUuid: string | null;
  onOpenResult: (result: SearchResult) => void;
  onBookshelfChange: (entry: BookshelfEntry) => void;
}) {
  return (
    <div className="mt-5 overflow-hidden rounded-lg border">
      <div className="flex items-center justify-between border-b bg-muted/40 px-4 py-2 text-sm font-medium">
        <span>Results</span>
        <small className="text-muted-foreground">{results.length}</small>
      </div>
      <div role="table" aria-label="Search results">
        <div className="grid grid-cols-[minmax(0,2fr)_minmax(0,3fr)_1.75rem] gap-4 border-b bg-muted/20 px-4 py-2 text-xs font-semibold uppercase text-muted-foreground" role="row">
          <span>Title</span>
          <span>One-liner</span>
          <span />
        </div>
        {results.map((result) => {
          const { document } = result;
          const selected = selectedDocumentUuid === document.uuid;
          return (
            <div
              key={document.uuid}
              className={`group grid cursor-pointer grid-cols-[minmax(0,2fr)_minmax(0,3fr)_1.75rem] items-center gap-4 border-b px-4 py-3 text-sm last:border-0 hover:bg-muted/50 ${
                selected ? 'bg-accent/60' : ''
              }`}
              role="row"
              tabIndex={0}
              aria-selected={selected}
              onClick={(event) => {
                const target = event.target as HTMLElement;
                if (target.closest('a, button')) return;
                onOpenResult(result);
              }}
              onKeyDown={(event) => {
                if (event.target !== event.currentTarget) return;
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  onOpenResult(result);
                }
              }}
            >
              <span className="min-w-0" data-label="Title" title={document.title ?? document.url}>
                <strong className="flex min-w-0 items-center gap-1.5 font-medium">
                  <span className="truncate">{document.title ?? document.url}</span>
                  <a className="shrink-0 text-muted-foreground hover:text-foreground" href={document.url} target="_blank" rel="noreferrer" aria-label="Open document" onClick={(event) => event.stopPropagation()}>
                    <ArrowUpRight size={14} />
                  </a>
                </strong>
              </span>
              <span className="min-w-0 truncate text-muted-foreground" data-label="One-liner" title={resultOneLiner(result)}>
                {resultOneLiner(result)}
              </span>
              <DocumentActionsMenu
                documentUuid={document.uuid}
                status={document.bookshelf_status}
                revealOnHover
                onBookshelfChange={onBookshelfChange}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}

function naturalRelevance(result: SearchResult): string {
  const text =
    result.document.one_liner?.trim() ||
    result.document.summary?.trim() ||
    cleanTechnicalReason(result.reason);
  return truncate(text || 'This result matched the search terms and corpus context.', 180);
}

function resultOneLiner(result: SearchResult): string {
  return truncate(result.document.one_liner?.trim() || 'No one-liner yet.', 180);
}

function cleanTechnicalReason(reason: string): string {
  return reason
    .replace(/^agent selected:\s*/i, '')
    .replace(/\b(keyword|semantic|tags|categories):\s*/gi, '')
    .replace(/\bpgvector cosine\s+\d+(?:\.\d+)?/gi, 'semantic match')
    .replace(/\bembedding cosine\s+\d+(?:\.\d+)?/gi, 'semantic match')
    .replace(/\bkeyword overlap\s+\d+%/gi, 'keyword match')
    .replace(/\s*;\s*/g, ', ')
    .trim();
}

function truncate(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength - 3).trimEnd()}...`;
}

function conversationTurns(messages: ChatMessage[]): ConversationTurn[] {
  return messages.flatMap((message, index) => {
    if (message.role !== 'user') return [];
    const response = messages[index + 1]?.role === 'assistant' ? messages[index + 1].content : '';
    return [{ id: message.id, query: message.content, response }];
  });
}

function messagesFromConversation(conversation: AgentConversation): ChatMessage[] {
  return conversation.messages
    .filter((message) => !isLegacySyntheticAssistantMessage(message))
    .map((message) => ({
      id: `saved-${message.id}`,
      role: message.role === 'user' ? 'user' : 'assistant',
      content: message.content,
      steps: message.steps?.filter((step) => !isSyntheticStep(step)),
      results: message.results,
      pending: false,
    }));
}

function MessageContent({ content }: { content: string }) {
  const blocks = content.split(/\n{2,}/).map((block) => block.trim()).filter(Boolean);
  if (blocks.length === 0) return null;
  return (
    <div className="grid gap-3 text-sm leading-7 [&_p]:whitespace-pre-wrap [&_ul]:list-disc [&_ul]:space-y-1 [&_ul]:pl-5">
      {blocks.map((block, blockIndex) => {
        const lines = block.split('\n').map((line) => line.trim()).filter(Boolean);
        const bulletLines = lines.filter((line) => line.startsWith('- '));
        if (bulletLines.length === lines.length) {
          return (
            <ul key={`${block}-${blockIndex}`}>
              {bulletLines.map((line, lineIndex) => (
                <li key={`${line}-${lineIndex}`}>{renderInlineMarkdown(line.slice(2))}</li>
              ))}
            </ul>
          );
        }
        return <p key={`${block}-${blockIndex}`}>{renderInlineMarkdown(block)}</p>;
      })}
    </div>
  );
}

function renderInlineMarkdown(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, index) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={`${part}-${index}`}>{part.slice(2, -2)}</strong>;
    }
    return part;
  });
}

function isSyntheticStep(step: AgentStep): boolean {
  if (step.kind !== 'tool') return true;
  if (step.title === 'Waiting for a corpus query') return true;
  if (step.title === 'Run OpenAI agent loop') return true;
  if (step.title === 'Agent final answer') return true;
  if (step.title === 'Persist selected citations') return true;
  return false;
}

function SearchTrace({
  steps,
  onOpenDocument,
}: {
  steps: AgentStep[];
  onOpenDocument: (document: AgentInspectedDocument) => void;
}) {
  const [traceOpen, setTraceOpen] = useState(false);
  const inspectedCount = steps.reduce((total, step) => total + (step.documents?.length ?? 0), 0);
  return (
    <details className="mt-4 text-muted-foreground" open={traceOpen} onToggle={(event) => setTraceOpen(event.currentTarget.open)}>
      <summary className="flex w-fit cursor-pointer list-none items-center gap-2 text-xs hover:text-foreground">
        <Search size={13} />
        <span>Search process</span>
        <span className="text-muted-foreground/70">{steps.length} {steps.length === 1 ? 'step' : 'steps'} · {inspectedCount} inspected</span>
        <ChevronDown className={`size-3 transition-transform ${traceOpen ? 'rotate-180' : ''}`} aria-hidden="true" />
      </summary>
      <div className="mt-2 ml-1 border-l pl-4">
        {steps.map((step, index) => (
          <details className="py-1" key={`${step.kind}-${step.title}-${step.query}-${index}`}>
            <summary className="grid cursor-pointer list-none grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-2 py-1 text-xs hover:text-foreground">
              <span className="text-muted-foreground/80">{traceIcon(step)}</span>
              <span className="min-w-0 truncate">
                <strong className="font-medium text-foreground/75">{traceTitle(step)}</strong>
                {step.query && !isInternalDocumentQuery(step) && <span className="ml-1.5 text-muted-foreground/80">{step.query}</span>}
              </span>
              {typeof step.hits === 'number' && <span className="text-muted-foreground/70">{step.hits} found</span>}
            </summary>
            <div className="grid gap-2 py-2 pl-5">
              {step.query && !isInternalDocumentQuery(step) && (
                <code className="overflow-x-auto text-xs text-muted-foreground">{step.query}</code>
              )}
              {step.documents?.length > 0 && (
                <div className="grid gap-1">
                  {step.documents.map((document, documentIndex) => (
                    <button
                      className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-4 rounded-md px-2 py-1.5 text-left text-xs hover:bg-muted hover:text-foreground"
                      key={`${document.uuid}-${documentIndex}`}
                      type="button"
                      onClick={() => onOpenDocument(document)}
                    >
                      <span className="min-w-0">
                        <strong className="block truncate font-medium text-foreground/80">{document.title}</strong>
                        <small className="block truncate text-muted-foreground">{document.source_domain}</small>
                      </span>
                      <em className="line-clamp-2 not-italic text-muted-foreground">{document.reason}</em>
                    </button>
                  ))}
                </div>
              )}
              {step.documents?.length === 0 && step.detail && (
                <p className="text-xs text-muted-foreground">{step.detail}</p>
              )}
            </div>
          </details>
        ))}
      </div>
    </details>
  );
}

function traceTitle(step: AgentStep): string {
  const tool = step.tool?.toLowerCase();
  if (tool === 'keyword') return 'Keyword search';
  if (tool === 'semantic') return 'Semantic search';
  if (tool === 'tags') return 'Tag search';
  if (tool === 'categories') return 'Category search';
  if (tool === 'document_metadata') return 'Inspect document';
  if (tool === 'source_metadata') return 'Inspect source';
  return step.title.replace(/^Run\s+/i, '');
}

function traceIcon(step: AgentStep) {
  const tool = step.tool?.toLowerCase();
  if (tool === 'semantic') return <BrainCircuit size={14} />;
  if (tool === 'keyword') return <Search size={14} />;
  if (tool === 'tags') return <Tags size={14} />;
  if (tool === 'categories') return <Hash size={14} />;
  return <FileSearch size={14} />;
}

function isInternalDocumentQuery(step: AgentStep) {
  return step.tool?.toLowerCase() === 'document_metadata' && /^\d+$/.test(step.query ?? '');
}

function traceDocumentReason(document: AgentInspectedDocument) {
  return `${document.source_domain} · ${document.reason}`;
}

function isLegacySyntheticAssistantMessage(message: AgentConversation['messages'][number]): boolean {
  if (message.role !== 'assistant') return false;
  if (message.results.length > 0) return false;
  const steps = message.steps ?? [];
  const onlySyntheticSteps = steps.length > 0 && steps.every(isSyntheticStep);
  return onlySyntheticSteps && message.content.includes('Tell me what you want to find in the corpus');
}
