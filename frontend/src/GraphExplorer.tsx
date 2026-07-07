import { FormEvent, PointerEvent, useEffect, useMemo, useRef, useState } from 'react';
import * as d3 from 'd3-force';
import { ArrowUpRight, FileText, Loader2, LocateFixed, Users } from 'lucide-react';
import { getGraph, searchGraphSources } from './api';
import { CorpusSearchForm } from './CorpusSearchForm';
import { StateMessage } from './components/ui';
import type { AdminSource, GraphEdge, GraphNode, GraphResponse } from './types';

type GraphMode = 'sources' | 'documents';
type LayoutNode = GraphNode & d3.SimulationNodeDatum & { x: number; y: number; r: number; color: string };
type RankedGraphReference = { edge: GraphEdge; node: LayoutNode };
type GraphReferenceDirection = 'inbound' | 'outbound';
type DragState =
  | { kind: 'canvas'; x: number; y: number; moved: boolean }
  | { kind: 'node'; id: string; x: number; y: number; moved: boolean };

const WIDTH = 1800;
const HEIGHT = 1000;

export function GraphExplorer({ onOpenProfile }: { onOpenProfile?: (sourceId: number, domain: string) => void }) {
  const [mode, setMode] = useState<GraphMode>('sources');
  const [depth, setDepth] = useState(1);
  const [domain, setDomain] = useState('');
  const [graph, setGraph] = useState<GraphResponse>({ nodes: [], edges: [] });
  const [sourceMatches, setSourceMatches] = useState<AdminSource[]>([]);
  const [searchOpen, setSearchOpen] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [layout, setLayout] = useState<LayoutNode[]>([]);
  const [panelOpen, setPanelOpen] = useState(true);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const dragRef = useRef<DragState | null>(null);
  const simulationRef = useRef<d3.Simulation<LayoutNode, undefined> | null>(null);
  const nodesRef = useRef<Map<string, LayoutNode>>(new Map());
  const searchWrapRef = useRef<HTMLDivElement | null>(null);
  const suppressClickRef = useRef(false);

  async function refresh(nextMode = mode, nextDomain = domain, focusId?: string, nextDepth = depth) {
    setLoading(true);
    setError(null);
    try {
      const params =
        focusId && nextMode === 'sources'
          ? { mode: nextMode, sourceId: numericNodeId(focusId), limit: 160, depth: nextDepth }
          : focusId && nextMode === 'documents'
            ? { mode: nextMode, documentId: numericNodeId(focusId), limit: 120 }
            : { mode: nextMode, domain: nextDomain.trim(), limit: nextMode === 'sources' ? 160 : 120, depth: nextDepth };
      const data = await getGraph(params);
      setGraph(data);
      setSelectedId(focusId && data.nodes.some((node) => node.id === focusId) ? focusId : data.nodes[0]?.id ?? null);
      setPanelOpen(true);
      setPan({ x: 0, y: 0 });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Graph failed');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      const editing = target?.tagName === 'INPUT' || target?.tagName === 'TEXTAREA' || target?.tagName === 'SELECT';
      if (editing || event.key.toLowerCase() !== 'r') return;
      event.preventDefault();
      setPan({ x: 0, y: 0 });
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  useEffect(() => {
    function handlePointerDown(event: globalThis.PointerEvent) {
      const target = event.target as Node | null;
      if (!target || searchWrapRef.current?.contains(target)) return;
      setSearchOpen(false);
    }
    window.addEventListener('pointerdown', handlePointerDown);
    return () => window.removeEventListener('pointerdown', handlePointerDown);
  }, []);

  useEffect(() => {
    simulationRef.current?.stop();
    const nodes = initialLayout(graph.nodes, graph.edges, mode);
    nodesRef.current = new Map(nodes.map((node) => [node.id, node]));
    setLayout(nodes.map((node) => ({ ...node })));
    const links = graph.edges
      .filter((edge) => nodesRef.current.has(edge.source) && nodesRef.current.has(edge.target))
      .map((edge) => ({ source: edge.source, target: edge.target, weight: edge.weight }));
    const simulation = d3
      .forceSimulation<LayoutNode>(nodes)
      .force(
        'link',
        d3
          .forceLink<LayoutNode, { source: string; target: string; weight: number }>(links)
          .id((node) => node.id)
          .distance((link) => Math.max(76, 150 - Math.sqrt(link.weight) * 8))
          .strength((link) => Math.min(0.28, 0.06 + link.weight * 0.012)),
      )
      .force('charge', d3.forceManyBody<LayoutNode>().strength((node) => -260 - node.r * 14))
      .force('collide', d3.forceCollide<LayoutNode>().radius((node) => node.r + 14).strength(0.8).iterations(2))
      .force('x', d3.forceX<LayoutNode>(WIDTH / 2).strength(0.035))
      .force('y', d3.forceY<LayoutNode>(HEIGHT / 2).strength(0.035))
      .alpha(0.95)
      .alphaDecay(0.035)
      .on('tick', () => {
        for (const node of nodes) {
          node.x = Math.max(-WIDTH * 0.35, Math.min(WIDTH * 1.35, node.x ?? WIDTH / 2));
          node.y = Math.max(-HEIGHT * 0.35, Math.min(HEIGHT * 1.35, node.y ?? HEIGHT / 2));
        }
        setLayout(nodes.map((node) => ({ ...node })));
    });
    simulationRef.current = simulation;
    return () => {
      simulation.stop();
    };
  }, [graph, mode]);

  const nodeById = useMemo(() => new Map(layout.map((node) => [node.id, node])), [layout]);
  const selected = selectedId ? nodeById.get(selectedId) : null;
  const activeId = hoveredId ?? selectedId;
  const visibleEdges = graph.edges.filter((edge) => nodeById.has(edge.source) && nodeById.has(edge.target));
  const inboundReferences = rankedGraphReferences(selectedId, visibleEdges, nodeById, 'inbound');
  const outboundReferences = rankedGraphReferences(selectedId, visibleEdges, nodeById, 'outbound');
  const matches = domain.trim()
    ? layout.filter((node) => node.label.toLowerCase().includes(domain.trim().toLowerCase()) || node.domain.toLowerCase().includes(domain.trim().toLowerCase())).slice(0, 8)
    : [];
  const visibleMatches = mode === 'sources' && domain.trim() ? sourceMatches : matches;
  const showMatches = searchOpen && visibleMatches.length > 0;

  useEffect(() => {
    if (mode !== 'sources') {
      setSourceMatches([]);
      return;
    }
    const query = domain.trim();
    if (!query) {
      setSourceMatches([]);
      return;
    }
    let cancelled = false;
    const timeout = window.setTimeout(() => {
      searchGraphSources(query)
        .then((items) => {
          if (!cancelled) setSourceMatches(items);
        })
        .catch(() => {
          if (!cancelled) setSourceMatches([]);
        });
    }, 140);
    return () => {
      cancelled = true;
      window.clearTimeout(timeout);
    };
  }, [domain, mode]);

  function updateMode(nextMode: GraphMode) {
    setMode(nextMode);
    refresh(nextMode, domain);
  }

  function updateDepth(nextDepth: number) {
    setDepth(nextDepth);
    if (mode === 'sources') refresh(mode, domain, selectedId ?? undefined, nextDepth);
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    setSearchOpen(false);
    const query = domain.trim();
    const match = exactSearchMatch(domain, layout);
    if (match) {
      openNodeGraph(match);
    } else if (mode === 'sources' && isSpecificDomainQuery(query)) {
      refresh(mode, normalizeDomainQuery(query));
    } else if (mode === 'sources' && sourceMatches[0]) {
      selectSourceSearchMatch(sourceMatches[0]);
    }
  }

  function openNodeGraph(node: LayoutNode) {
    setDomain(node.domain);
    refresh(mode, mode === 'sources' ? node.domain : domain, node.id);
  }

  function openProfile(node: LayoutNode) {
    const sourceId = numericNodeId(node.id);
    if (sourceId === undefined) return;
    onOpenProfile?.(sourceId, node.domain);
  }

  function selectGraphNode(nodeId: string) {
    setSelectedId(nodeId);
    setPanelOpen(true);
  }

  function selectSearchMatch(node: LayoutNode) {
    setSearchOpen(false);
    setDomain(node.domain);
    openNodeGraph(node);
  }

  function selectSourceSearchMatch(source: AdminSource) {
    setSearchOpen(false);
    setDomain(source.canonical_domain);
    refresh('sources', source.canonical_domain, `source:${source.id}`);
  }

  function pointerDown(event: PointerEvent<SVGSVGElement>) {
    dragRef.current = { kind: 'canvas', x: event.clientX, y: event.clientY, moved: false };
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function pointerMove(event: PointerEvent<SVGSVGElement>) {
    if (!dragRef.current) return;
    const dx = event.clientX - dragRef.current.x;
    const dy = event.clientY - dragRef.current.y;
    if (Math.abs(dx) + Math.abs(dy) > 2) dragRef.current.moved = true;
    if (dragRef.current.kind === 'node') {
      const nodeId = dragRef.current.id;
      const node = nodesRef.current.get(nodeId);
      if (node) {
        node.fx = (node.fx ?? node.x ?? WIDTH / 2) + dx * 1.35;
        node.fy = (node.fy ?? node.y ?? HEIGHT / 2) + dy * 1.35;
        simulationRef.current?.alphaTarget(0.32).restart();
      }
    } else {
      setPan((current) => ({ x: current.x + dx * 1.35, y: current.y + dy * 1.35 }));
    }
    dragRef.current.x = event.clientX;
    dragRef.current.y = event.clientY;
  }

  function pointerUp(event: PointerEvent<SVGSVGElement>) {
    const drag = dragRef.current;
    suppressClickRef.current = drag?.moved ?? false;
    if (drag?.kind === 'node') {
      const node = nodesRef.current.get(drag.id);
      if (node) {
        node.fx = null;
        node.fy = null;
      }
      if (!drag.moved) {
        selectGraphNode(drag.id);
      }
      simulationRef.current?.alphaTarget(0).restart();
    }
    dragRef.current = null;
    event.currentTarget.releasePointerCapture(event.pointerId);
    window.setTimeout(() => {
      suppressClickRef.current = false;
    }, 0);
  }

  function nodePointerDown(event: PointerEvent<SVGGElement>, node: LayoutNode) {
    event.stopPropagation();
    const liveNode = nodesRef.current.get(node.id);
    if (liveNode) {
      liveNode.fx = liveNode.x;
      liveNode.fy = liveNode.y;
    }
    simulationRef.current?.alphaTarget(0.32).restart();
    dragRef.current = { kind: 'node', id: node.id, x: event.clientX, y: event.clientY, moved: false };
    event.currentTarget.ownerSVGElement?.setPointerCapture(event.pointerId);
  }

  return (
    <section className="graph-view">
      <div className="graph-toolbar">
        <div className="graph-search-wrap" ref={searchWrapRef} onFocusCapture={() => setSearchOpen(true)}>
          <CorpusSearchForm
            className="graph-search"
            value={domain}
            onChange={(value) => {
              setDomain(value);
              setSearchOpen(true);
            }}
            onSubmit={submit}
            placeholder={mode === 'sources' ? 'focus domain, e.g. example.com' : 'filter title/domain'}
          />
          {showMatches && (
            <div className="graph-matches">
              {mode === 'sources'
                ? sourceMatches.map((source) => (
                    <button key={source.id} type="button" onClick={() => selectSourceSearchMatch(source)}>
                      <span>{source.canonical_domain}</span>
                      <small>{source.canonical_domain}</small>
                    </button>
                  ))
                : matches.map((node) => (
                    <button key={node.id} type="button" onClick={() => selectSearchMatch(node)}>
                      <span>{node.label}</span>
                      <small>{node.domain}</small>
                    </button>
                  ))}
            </div>
          )}
        </div>
        <div className="segmented">
          {mode === 'sources' && (
            <div className="graph-depth" aria-label="Graph depth">
              {[1, 2, 3].map((value) => (
                <button key={value} type="button" className={depth === value ? 'active' : ''} onClick={() => updateDepth(value)}>
                  {value}
                </button>
              ))}
            </div>
          )}
          <button type="button" className={mode === 'sources' ? 'active' : ''} onClick={() => updateMode('sources')}>
            <Users size={16} /> People
          </button>
          <button type="button" className={mode === 'documents' ? 'active' : ''} onClick={() => updateMode('documents')}>
            <FileText size={16} /> Docs
          </button>
        </div>
      </div>

      {error && <StateMessage className="error" tone="error">{error}</StateMessage>}
      <div className="graph-layout">
        <div className="graph-canvas-wrap">
          {loading && (
            <div className="graph-loading" aria-live="polite">
              <Loader2 size={22} />
              <span>Loading graph</span>
            </div>
          )}
          {!loading && graph.nodes.length === 0 && <StateMessage className="graph-loading">No graph neighbors found.</StateMessage>}
          <svg
            className="graph-canvas"
            viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
            role="img"
            onPointerDown={pointerDown}
            onPointerMove={pointerMove}
            onPointerUp={pointerUp}
            onPointerLeave={() => {
              dragRef.current = null;
            }}
            onWheel={(event) => {
              event.preventDefault();
            }}
          >
            <defs>
              <marker id="graph-arrow-active" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="3.5" markerHeight="3.5" orient="auto-start-reverse">
                <path d="M 0 0 L 10 5 L 0 10 z" />
              </marker>
            </defs>
            <g transform={`translate(${pan.x} ${pan.y})`}>
              {visibleEdges.map((edge, index) => {
                const source = nodeById.get(edge.source);
                const target = nodeById.get(edge.target);
                if (!source || !target) return null;
                const active = activeId === edge.source || activeId === edge.target;
                const hasReverse = visibleEdges.some((other) => other.source === edge.target && other.target === edge.source);
                const path = edgePath(source, target, hasReverse, edge.source < edge.target ? 1 : -1);
                return (
                  <path
                    key={`${edge.source}-${edge.target}-${index}`}
                    d={path}
                    className={active ? 'graph-edge active' : 'graph-edge'}
                    strokeWidth={edgeWidth(edge.weight, mode)}
                    markerEnd={active ? 'url(#graph-arrow-active)' : undefined}
                  />
                );
              })}
              {layout.map((node) => {
                const active = activeId === node.id;
                const related = activeId ? visibleEdges.some((edge) => (edge.source === activeId && edge.target === node.id) || (edge.target === activeId && edge.source === node.id)) : false;
                const labeled = active || related || node.r >= 17;
                return (
                  <g
                    key={node.id}
                    className={active ? 'graph-node active' : related ? 'graph-node related' : activeId ? 'graph-node muted' : 'graph-node'}
                    transform={`translate(${node.x} ${node.y})`}
                    onMouseEnter={() => setHoveredId(node.id)}
                    onMouseLeave={() => setHoveredId(null)}
                    onPointerDown={(event) => nodePointerDown(event, node)}
                    onClick={() => {
                      if (suppressClickRef.current) return;
                      selectGraphNode(node.id);
                    }}
                    onDoubleClick={() => openNodeGraph(node)}
                  >
                    <circle r={node.r} style={{ fill: node.color }} />
                    {labeled && <text y={node.r + 13}>{shortLabel(node.label)}</text>}
                  </g>
                );
              })}
            </g>
          </svg>
        </div>
        {selected && !panelOpen && (
          <button className="graph-panel-tab" type="button" onClick={() => setPanelOpen(true)}>
            {shortLabel(selected.label)}
          </button>
        )}
        {panelOpen && (
        <aside className="graph-panel">
          {selected ? (
            <>
              <div className="graph-title-row">
                <h3>{selected.label}</h3>
                <div className="graph-title-actions" aria-label="Graph actions">
                  {mode === 'sources' && (
                    <button type="button" onClick={() => openProfile(selected)} aria-label="Open profile" data-tooltip="Open profile" data-tooltip-placement="left">
                      <Users size={16} />
                    </button>
                  )}
                  <button type="button" onClick={() => openNodeGraph(selected)} aria-label="Open this graph" data-tooltip="Open this graph" data-tooltip-placement="left">
                    <LocateFixed size={16} />
                  </button>
                  {selected.url && (
                    <a href={selected.url} target="_blank" rel="noreferrer" aria-label="Open source" data-tooltip="Open source" data-tooltip-placement="left">
                      <ArrowUpRight size={16} />
                    </a>
                  )}
                </div>
              </div>
              <p>{selected.subtitle || selected.domain}</p>
              {selected.summary && <p>{selected.summary}</p>}
              <div className="graph-stats">
                <span>{graph.nodes.length} nodes</span>
                <span>{visibleEdges.length} edges</span>
                <span>{inboundReferences.length} referenced by</span>
                <span>{outboundReferences.length} references</span>
              </div>
              <GraphReferenceSection title="Referenced by" emptyLabel="No visible inbound references." items={inboundReferences} mode={mode} onSelect={selectGraphNode} />
              <GraphReferenceSection title="References" emptyLabel="No visible outbound references." items={outboundReferences} mode={mode} onSelect={selectGraphNode} />
            </>
          ) : (
            <p>Select a node.</p>
          )}
        </aside>
        )}
      </div>
    </section>
  );
}

function GraphReferenceSection({
  title,
  emptyLabel,
  items,
  mode,
  onSelect,
}: {
  title: string;
  emptyLabel: string;
  items: RankedGraphReference[];
  mode: GraphMode;
  onSelect: (nodeId: string) => void;
}) {
  return (
    <section className="graph-reference-section" aria-label={title}>
      <h4>{title}</h4>
      {items.length === 0 ? (
        <p className="graph-reference-empty">{emptyLabel}</p>
      ) : (
        <div className="graph-reference-list">
          {items.map((item) => (
            <button key={`${item.edge.source}-${item.edge.target}-${item.node.id}`} type="button" onClick={() => onSelect(item.node.id)}>
              <span className="graph-reference-copy">
                <strong>{item.node.label}</strong>
                <small>{graphReferenceMeta(item.node, item.edge)}</small>
              </span>
              <span className="graph-reference-weight">{graphReferenceWeightLabel(item.edge, mode)}</span>
            </button>
          ))}
        </div>
      )}
    </section>
  );
}

function rankedGraphReferences(
  selectedId: string | null,
  edges: GraphEdge[],
  nodeById: Map<string, LayoutNode>,
  direction: GraphReferenceDirection,
): RankedGraphReference[] {
  if (!selectedId) return [];
  return edges
    .filter((edge) => (direction === 'inbound' ? edge.target === selectedId : edge.source === selectedId))
    .map((edge) => {
      const relatedId = direction === 'inbound' ? edge.source : edge.target;
      const node = nodeById.get(relatedId);
      return node ? { edge, node } : null;
    })
    .filter((item): item is RankedGraphReference => item !== null)
    .sort((a, b) => b.edge.weight - a.edge.weight || a.node.label.localeCompare(b.node.label))
    .slice(0, 12);
}

function graphReferenceMeta(node: LayoutNode, edge: GraphEdge) {
  return edge.label ? `${node.domain} / ${edge.label}` : node.domain;
}

function graphReferenceWeightLabel(edge: GraphEdge, mode: GraphMode) {
  if (mode === 'documents') return edge.weight > 1 ? `${edge.weight} refs` : '1 ref';
  const count = Math.round(edge.weight);
  return `${count} link${count === 1 ? '' : 's'}`;
}

function exactSearchMatch(query: string, nodes: LayoutNode[]): LayoutNode | null {
  const normalized = normalizeDomainQuery(query);
  if (!normalized) return null;
  return nodes.find((node) => node.domain.toLowerCase() === normalized || node.label.toLowerCase() === normalized) ?? null;
}

function isSpecificDomainQuery(query: string): boolean {
  const normalized = normalizeDomainQuery(query);
  return /^[a-z0-9-]+(\.[a-z0-9-]+)+$/.test(normalized);
}

function normalizeDomainQuery(query: string): string {
  return query
    .trim()
    .toLowerCase()
    .replace(/^https?:\/\//, '')
    .replace(/^www\./, '')
    .replace(/\/.*$/, '');
}

function initialLayout(nodes: GraphNode[], edges: GraphEdge[], mode: GraphMode): LayoutNode[] {
  const ids = new Set(nodes.map((node) => node.id));
  const degrees = new Map(nodes.map((node) => [node.id, 0]));
  for (const edge of edges) {
    if (!ids.has(edge.source) || !ids.has(edge.target)) continue;
    degrees.set(edge.source, (degrees.get(edge.source) ?? 0) + edge.weight);
    degrees.set(edge.target, (degrees.get(edge.target) ?? 0) + edge.weight);
  }
  const positioned = nodes.map((node, index) => {
    const angle = (index / Math.max(1, nodes.length)) * Math.PI * 2;
    const ring = 230 + (index % 7) * 48;
    const degree = degrees.get(node.id) ?? 0;
    return {
      ...node,
      x: WIDTH / 2 + Math.cos(angle) * ring,
      y: HEIGHT / 2 + Math.sin(angle) * ring,
      r: Math.max(6, Math.min(30, 6 + Math.sqrt(degree || node.size) * 1.15)),
      color: colorForNode(node, mode),
    };
  });
  return positioned;
}

function colorForNode(node: GraphNode, mode: GraphMode) {
  const key = mode === 'documents' ? node.subtitle || node.domain : node.domain;
  let hash = 0;
  for (let index = 0; index < key.length; index += 1) {
    hash = (hash * 31 + key.charCodeAt(index)) >>> 0;
  }
  const hue = hash % 360;
  return `hsl(${hue} ${mode === 'documents' ? '38%' : '32%'} ${mode === 'documents' ? '84%' : '82%'})`;
}

function edgePath(source: LayoutNode, target: LayoutNode, curved: boolean, curveSign: number) {
  const dx = target.x - source.x;
  const dy = target.y - source.y;
  const distance = Math.hypot(dx, dy) || 1;
  const ux = dx / distance;
  const uy = dy / distance;
  const x1 = source.x + ux * (source.r + 2);
  const y1 = source.y + uy * (source.r + 2);
  const x2 = target.x - ux * (target.r + 5);
  const y2 = target.y - uy * (target.r + 5);
  if (!curved) return `M ${x1} ${y1} L ${x2} ${y2}`;

  const offset = Math.min(38, Math.max(18, distance * 0.08));
  const cx = (x1 + x2) / 2 + -uy * offset * curveSign;
  const cy = (y1 + y2) / 2 + ux * offset * curveSign;
  return `M ${x1} ${y1} Q ${cx} ${cy} ${x2} ${y2}`;
}

function edgeWidth(weight: number, mode: GraphMode) {
  const base = Math.sqrt(weight);
  return mode === 'sources' ? Math.max(0.45, Math.min(1.35, base * 0.62)) : Math.max(0.7, Math.min(3.2, base));
}

function numericNodeId(id: string) {
  const value = Number(id.split(':')[1]);
  return Number.isFinite(value) ? value : undefined;
}

function shortLabel(label: string) {
  return label.length > 24 ? `${label.slice(0, 22)}...` : label;
}
