import { useEffect, useMemo, useRef, useState } from 'react';
import { ArrowUpRight, Crosshair, HelpCircle, Loader2, MousePointer2 } from 'lucide-react';
import * as THREE from 'three';
import { getEmbeddingMap, getEmbeddingNeighbors } from './api';
import { CorpusSearchForm } from './CorpusSearchForm';
import type { EmbeddingMap, EmbeddingMapPoint, EmbeddingNeighbor } from './types';

type HoverState = {
  point: EmbeddingMapPoint;
  x: number;
  y: number;
} | null;

const CLUSTER_COLORS = [
  '#47c2ff',
  '#55d68f',
  '#f2c14e',
  '#f78166',
  '#b884ff',
  '#66d9e8',
  '#ff8bd1',
  '#a3e635',
  '#f59e0b',
  '#7dd3fc',
  '#c084fc',
  '#fb7185',
  '#34d399',
  '#facc15',
  '#60a5fa',
  '#f97316',
  '#2dd4bf',
  '#e879f9',
  '#bef264',
  '#a78bfa',
  '#22c55e',
  '#fb923c',
  '#38bdf8',
  '#eab308',
];

const SCENE_SPREAD = 2.65;
const Z_SPREAD = 1.7;
const MIN_RENDER_GAP = 3.1;
const TRACKING_KEYS = new Set(['fbclid', 'gclid', 'mc_cid', 'mc_eid', 'ref']);

function colorForCluster(clusterId: number | null) {
  if (clusterId == null) return new THREE.Color('#9ca3af');
  return new THREE.Color(CLUSTER_COLORS[Math.abs(clusterId) % CLUSTER_COLORS.length]);
}

function colorForDomain(domain: string) {
  let hash = 0;
  for (let index = 0; index < domain.length; index += 1) {
    hash = (hash * 31 + domain.charCodeAt(index)) >>> 0;
  }
  const color = new THREE.Color();
  color.setHSL((hash % 360) / 360, 0.9, 0.62);
  return color;
}

function colorForPoint(point: EmbeddingMapPoint) {
  return point.cluster_id == null ? colorForDomain(point.document.source_domain) : colorForCluster(point.cluster_id);
}

function scenePosition(point: EmbeddingMapPoint) {
  return new THREE.Vector3(point.x * SCENE_SPREAD, point.y * SCENE_SPREAD, point.z * SCENE_SPREAD * Z_SPREAD);
}

function deterministicJitter(seed: number) {
  const a = Math.sin(seed * 12.9898) * 43758.5453;
  const b = Math.sin(seed * 78.233) * 24634.6345;
  const c = Math.sin(seed * 37.719) * 19341.1234;
  return new THREE.Vector3(a - Math.floor(a) - 0.5, b - Math.floor(b) - 0.5, c - Math.floor(c) - 0.5).multiplyScalar(1.35);
}

function separatedScenePositions(points: EmbeddingMapPoint[]) {
  const positions = points.map((point) => scenePosition(point).add(deterministicJitter(point.document.id)));
  for (let pass = 0; pass < 4; pass += 1) {
    for (let left = 0; left < positions.length; left += 1) {
      for (let right = left + 1; right < positions.length; right += 1) {
        const delta = positions[left].clone().sub(positions[right]);
        const distance = delta.length();
        if (distance >= MIN_RENDER_GAP) continue;
        const direction = distance > 0.001 ? delta.multiplyScalar(1 / distance) : deterministicJitter(left + right + pass).normalize();
        const push = (MIN_RENDER_GAP - distance) * 0.28;
        positions[left].addScaledVector(direction, push);
        positions[right].addScaledVector(direction, -push);
      }
    }
  }
  return positions;
}

function focusedPoint(
  camera: THREE.PerspectiveCamera,
  points: EmbeddingMapPoint[],
  renderPositions: Map<number, THREE.Vector3>,
) {
  let best: EmbeddingMapPoint | null = null;
  let bestDistance = 0.08;
  const projected = new THREE.Vector3();
  for (const point of points) {
    const position = renderPositions.get(point.document.id);
    if (!position) continue;
    projected.copy(position).project(camera);
    if (projected.z < -1 || projected.z > 1) continue;
    const distance = Math.hypot(projected.x, projected.y);
    if (distance < bestDistance) {
      best = point;
      bestDistance = distance;
    }
  }
  return best;
}

function createHolographicPointTexture() {
  const canvas = document.createElement('canvas');
  canvas.width = 48;
  canvas.height = 48;
  const context = canvas.getContext('2d');
  if (!context) return null;

  const glow = context.createRadialGradient(24, 24, 4, 24, 24, 24);
  glow.addColorStop(0, 'rgba(255, 255, 255, 0.78)');
  glow.addColorStop(0.34, 'rgba(255, 255, 255, 0.24)');
  glow.addColorStop(1, 'rgba(255, 255, 255, 0)');
  context.fillStyle = glow;
  context.fillRect(0, 0, 48, 48);

  context.fillStyle = 'rgba(255, 255, 255, 0.82)';
  context.fillRect(14, 14, 20, 20);
  context.strokeStyle = 'rgba(255, 255, 255, 0.38)';
  context.lineWidth = 2;
  context.strokeRect(13, 13, 22, 22);

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.needsUpdate = true;
  return texture;
}

function createHighlightTexture() {
  const canvas = document.createElement('canvas');
  canvas.width = 64;
  canvas.height = 64;
  const context = canvas.getContext('2d');
  if (!context) return null;
  context.clearRect(0, 0, 64, 64);
  context.strokeStyle = 'rgba(17, 17, 17, 0.82)';
  context.lineWidth = 4;
  context.strokeRect(18, 18, 28, 28);
  context.strokeStyle = 'rgba(255, 255, 255, 0.82)';
  context.lineWidth = 2;
  context.strokeRect(20, 20, 24, 24);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.needsUpdate = true;
  return texture;
}

function createHoverTexture() {
  const canvas = document.createElement('canvas');
  canvas.width = 64;
  canvas.height = 64;
  const context = canvas.getContext('2d');
  if (!context) return null;
  context.clearRect(0, 0, 64, 64);
  context.strokeStyle = 'rgba(17, 17, 17, 0.46)';
  context.lineWidth = 3;
  context.strokeRect(20, 20, 24, 24);
  context.strokeStyle = 'rgba(255, 255, 255, 0.64)';
  context.lineWidth = 2;
  context.strokeRect(22, 22, 20, 20);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.needsUpdate = true;
  return texture;
}

export function EmbeddingExplorer() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const pointsRef = useRef<THREE.Points | null>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);
  const selectedRef = useRef<EmbeddingMapPoint | null>(null);
  const dataRef = useRef<EmbeddingMapPoint[]>([]);
  const renderPositionsRef = useRef<Map<number, THREE.Vector3>>(new Map());
  const yawRef = useRef(-0.75);
  const pitchRef = useRef(0.05);
  const cameraPositionRef = useRef(new THREE.Vector3(-155, 19, 136));
  const dragRef = useRef<{ x: number; y: number; active: boolean }>({ x: 0, y: 0, active: false });
  const keysRef = useRef<Set<string>>(new Set());
  const centerHitRef = useRef<EmbeddingMapPoint | null>(null);

  const [map, setMap] = useState<EmbeddingMap | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [hover, setHover] = useState<HoverState>(null);
  const [selected, setSelected] = useState<EmbeddingMapPoint | null>(null);
  const [neighbors, setNeighbors] = useState<EmbeddingNeighbor[]>([]);
  const [neighborsLoading, setNeighborsLoading] = useState(false);
  const [showHelp, setShowHelp] = useState(false);
  const [flightActive, setFlightActive] = useState(false);

  const searchMatches = useMemo(() => {
    const normalized = normalizeUrlForLookup(query);
    if (!normalized || !map) return [];
    return map.points
      .filter((point) => {
        return normalizeUrlForLookup(point.document.url) === normalized;
      })
      .slice(0, 6);
  }, [map, query]);

  useEffect(() => {
    let mounted = true;
    getEmbeddingMap()
      .then((payload) => {
        if (!mounted) return;
        setMap(payload);
        dataRef.current = payload.points;
        setSelected(payload.points[0] ?? null);
        selectedRef.current = payload.points[0] ?? null;
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Embedding map failed'))
      .finally(() => mounted && setLoading(false));
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    if (!selected) {
      setNeighbors([]);
      return;
    }
    let mounted = true;
    setNeighborsLoading(true);
    getEmbeddingNeighbors(selected.document.id, 5)
      .then((payload) => {
        if (mounted) setNeighbors(payload);
      })
      .catch(() => {
        if (mounted) setNeighbors([]);
      })
      .finally(() => {
        if (mounted) setNeighborsLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, [selected]);

  useEffect(() => {
    if (!canvasRef.current || !map) return;
    const mapPoints = map.points;
    const canvas = canvasRef.current;
    const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    rendererRef.current = renderer;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color('#ffffff');
    scene.fog = new THREE.Fog('#ffffff', 190, 520);
    sceneRef.current = scene;

    const camera = new THREE.PerspectiveCamera(58, 1, 0.1, 1000);
    cameraRef.current = camera;

    const geometry = new THREE.BufferGeometry();
    const positions = new Float32Array(mapPoints.length * 3);
    const baseColors = new Float32Array(mapPoints.length * 3);
    const colors = new Float32Array(mapPoints.length * 3);
    const renderPositions = separatedScenePositions(mapPoints);
    renderPositionsRef.current = new Map(
      mapPoints.map((point, index) => [point.document.id, renderPositions[index].clone()]),
    );
    mapPoints.forEach((point, index) => {
      positions[index * 3] = renderPositions[index].x;
      positions[index * 3 + 1] = renderPositions[index].y;
      positions[index * 3 + 2] = renderPositions[index].z;
      const color = colorForPoint(point);
      baseColors[index * 3] = color.r;
      baseColors[index * 3 + 1] = color.g;
      baseColors[index * 3 + 2] = color.b;
      colors[index * 3] = color.r;
      colors[index * 3 + 1] = color.g;
      colors[index * 3 + 2] = color.b;
    });
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    const colorAttribute = new THREE.BufferAttribute(colors, 3);
    geometry.setAttribute('color', colorAttribute);

    const pointTexture = createHolographicPointTexture();
    const material = new THREE.PointsMaterial({
      size: 2.08,
      map: pointTexture ?? undefined,
      vertexColors: true,
      transparent: true,
      opacity: 0.88,
      sizeAttenuation: true,
      alphaTest: 0.03,
      blending: THREE.NormalBlending,
      depthWrite: false,
      toneMapped: false,
    });
    const pointCloud = new THREE.Points(geometry, material);
    pointsRef.current = pointCloud;
    scene.add(pointCloud);

    const grid = new THREE.GridHelper(240, 24, '#d8d8d8', '#eeeeee');
    grid.position.y = -95;
    scene.add(grid);
    scene.add(new THREE.AmbientLight('#ffffff', 1));

    const highlightTexture = createHighlightTexture();
    const hoverTexture = createHoverTexture();
    const hoverMarker = new THREE.Sprite(
      new THREE.SpriteMaterial({
        map: hoverTexture ?? undefined,
        transparent: true,
        opacity: 0.68,
        depthTest: false,
        depthWrite: false,
      }),
    );
    hoverMarker.scale.set(5.8, 5.8, 1);
    hoverMarker.renderOrder = 3;
    hoverMarker.visible = false;
    scene.add(hoverMarker);

    const selectedMarker = new THREE.Sprite(
      new THREE.SpriteMaterial({
        map: highlightTexture ?? undefined,
        transparent: true,
        opacity: 0.92,
        depthTest: false,
        depthWrite: false,
      }),
    );
    selectedMarker.scale.set(7.2, 7.2, 1);
    selectedMarker.renderOrder = 4;
    selectedMarker.visible = false;
    scene.add(selectedMarker);
    let frameId = 0;

    function resize() {
      const rect = canvas.getBoundingClientRect();
      const width = Math.max(1, Math.floor(rect.width));
      const height = Math.max(1, Math.floor(rect.height));
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
    }

    function updateCamera() {
      const pitch = pitchRef.current;
      const yaw = yawRef.current;
      const position = cameraPositionRef.current;
      camera.position.copy(position);
      camera.rotation.set(pitch, yaw, 0, 'YXZ');
    }

    function updateDistanceFade() {
      for (let index = 0; index < mapPoints.length; index += 1) {
        const dx = positions[index * 3] - camera.position.x;
        const dy = positions[index * 3 + 1] - camera.position.y;
        const dz = positions[index * 3 + 2] - camera.position.z;
        const distance = Math.hypot(dx, dy, dz);
        const fade = Math.max(0, Math.min(1, (distance - 70) / 190));
        const whiteMix = fade * 0.9;
        colors[index * 3] = baseColors[index * 3] + (1 - baseColors[index * 3]) * whiteMix;
        colors[index * 3 + 1] = baseColors[index * 3 + 1] + (1 - baseColors[index * 3 + 1]) * whiteMix;
        colors[index * 3 + 2] = baseColors[index * 3 + 2] + (1 - baseColors[index * 3 + 2]) * whiteMix;
      }
      colorAttribute.needsUpdate = true;
    }

    function animate() {
      frameId = requestAnimationFrame(animate);
      resize();
      updateCamera();
      const speed = keysRef.current.has('shift') ? 1.55 : 0.62;
      const forward = new THREE.Vector3();
      camera.getWorldDirection(forward);
      forward.normalize();
      const right = new THREE.Vector3().crossVectors(forward, camera.up).normalize();
      const position = cameraPositionRef.current;
      if (keysRef.current.has('w')) position.addScaledVector(forward, speed);
      if (keysRef.current.has('s')) position.addScaledVector(forward, -speed);
      if (keysRef.current.has('a')) position.addScaledVector(right, -speed);
      if (keysRef.current.has('d')) position.addScaledVector(right, speed);
      if (keysRef.current.has(' ')) position.y += speed;
      if (keysRef.current.has('control')) position.y -= speed;
      updateCamera();
      updateDistanceFade();

      if (selectedRef.current) {
        selectedMarker.visible = true;
        selectedMarker.position.copy(renderPositionsRef.current.get(selectedRef.current.document.id) ?? scenePosition(selectedRef.current));
      } else {
        selectedMarker.visible = false;
      }

      const centerHit = focusedPoint(camera, mapPoints, renderPositionsRef.current);
      if (centerHit) {
        const rect = canvas.getBoundingClientRect();
        const point = centerHit;
        centerHitRef.current = point;
        hoverMarker.visible = selectedRef.current?.document.id !== point.document.id;
        hoverMarker.position.copy(renderPositionsRef.current.get(point.document.id) ?? scenePosition(point));
        setHover({
          point,
          x: rect.width / 2,
          y: rect.height / 2,
        });
      } else {
        centerHitRef.current = null;
        hoverMarker.visible = false;
        setHover(null);
      }
      renderer.render(scene, camera);
    }
    animate();

    const flightKeys = new Set(['w', 'a', 's', 'd', 'shift', ' ', 'control']);
    const handleKeyDown = (event: KeyboardEvent) => {
      const key = event.key.toLowerCase();
      const target = event.target as HTMLElement | null;
      const editing = target?.tagName === 'INPUT' || target?.tagName === 'TEXTAREA' || target?.tagName === 'SELECT';
      if (editing && document.pointerLockElement !== canvas) return;
      if (flightKeys.has(key)) event.preventDefault();
      keysRef.current.add(key);
    };
    const handleKeyUp = (event: KeyboardEvent) => keysRef.current.delete(event.key.toLowerCase());
    const handleMouseMove = (event: MouseEvent) => {
      if (document.pointerLockElement !== canvas) return;
      yawRef.current -= event.movementX * 0.0025;
      pitchRef.current = Math.max(-1.45, Math.min(1.45, pitchRef.current - event.movementY * 0.0025));
    };
    const handlePointerLockChange = () => setFlightActive(document.pointerLockElement === canvas);
    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('keyup', handleKeyUp);
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('pointerlockchange', handlePointerLockChange);

    return () => {
      cancelAnimationFrame(frameId);
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('keyup', handleKeyUp);
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('pointerlockchange', handlePointerLockChange);
      renderer.dispose();
      geometry.dispose();
      pointTexture?.dispose();
      highlightTexture?.dispose();
      hoverTexture?.dispose();
      material.dispose();
      hoverMarker.geometry.dispose();
      const hoverMaterial = hoverMarker.material;
      if (Array.isArray(hoverMaterial)) {
        hoverMaterial.forEach((item) => item.dispose());
      } else {
        hoverMaterial.dispose();
      }
      selectedMarker.geometry.dispose();
      const markerMaterial = selectedMarker.material;
      if (Array.isArray(markerMaterial)) {
        markerMaterial.forEach((item) => item.dispose());
      } else {
        markerMaterial.dispose();
      }
    };
  }, [map]);

  function selectPoint(point: EmbeddingMapPoint, options: { teleport?: boolean } = {}) {
    setSelected(point);
    selectedRef.current = point;
    if (!options.teleport) return;
    const camera = cameraRef.current;
    const direction = new THREE.Vector3();
    if (camera) {
      camera.getWorldDirection(direction);
    } else {
      direction.set(0, 0, -1);
    }
    cameraPositionRef.current.copy(renderPositionsRef.current.get(point.document.id) ?? scenePosition(point)).addScaledVector(direction, -42);
  }

  function selectCenterHit() {
    if (centerHitRef.current) selectPoint(centerHitRef.current);
  }

  function selectSearchMatch(point: EmbeddingMapPoint) {
    selectPoint(point, { teleport: true });
    setQuery('');
  }

  return (
    <section className="explorer-shell">
      <div className="explorer-toolbar">
        <CorpusSearchForm
          className="explorer-teleport"
          value={query}
          onChange={setQuery}
          onSubmit={(event) => {
            event.preventDefault();
            if (searchMatches[0]) selectSearchMatch(searchMatches[0]);
          }}
          placeholder="Paste URL..."
          disabled={!searchMatches[0]}
        >
          {searchMatches.length > 0 && (
            <div className="explorer-search-results">
              {searchMatches.map((point) => (
                <button key={point.document.id} type="button" onClick={() => selectSearchMatch(point)}>
                  <span>{point.document.title || point.document.url}</span>
                  <small>{point.document.source_domain}</small>
                </button>
              ))}
            </div>
          )}
          {normalizeUrlForLookup(query) && searchMatches.length === 0 && (
            <div className="explorer-search-results explorer-search-empty">
              No document with that URL.
            </div>
          )}
        </CorpusSearchForm>
      </div>

      <div className="explorer-stage">
        <canvas
          ref={canvasRef}
          className="explorer-canvas"
          onPointerMove={(event) => {
            if (!dragRef.current.active) return;
            const dx = event.clientX - dragRef.current.x;
            const dy = event.clientY - dragRef.current.y;
            yawRef.current -= dx * 0.004;
            pitchRef.current = Math.max(-1.45, Math.min(1.45, pitchRef.current - dy * 0.004));
            dragRef.current = { x: event.clientX, y: event.clientY, active: true };
          }}
          onPointerDown={(event) => {
            event.currentTarget.requestPointerLock?.();
            dragRef.current = { x: event.clientX, y: event.clientY, active: true };
            event.currentTarget.setPointerCapture(event.pointerId);
          }}
          onPointerUp={(event) => {
            dragRef.current.active = false;
            event.currentTarget.releasePointerCapture(event.pointerId);
            selectCenterHit();
          }}
          onPointerLeave={() => {
            dragRef.current.active = false;
          }}
          onWheel={(event) => {
            const camera = cameraRef.current;
            if (!camera) return;
            const direction = new THREE.Vector3();
            camera.getWorldDirection(direction);
            cameraPositionRef.current.addScaledVector(direction, event.deltaY * -0.035);
          }}
        />
        {loading && (
          <div className="explorer-loading" aria-live="polite">
            <Loader2 size={22} />
            <span>Loading map</span>
          </div>
        )}
        <div className="explorer-crosshair"><Crosshair size={24} /></div>
        {hover && (
          <div className="explorer-focus-label">
            <strong>{hover.point.document.title || hover.point.document.url}</strong>
            <span>{hover.point.document.source_domain}</span>
          </div>
        )}
        {!flightActive && (
          <div className="explorer-start">Click canvas to fly · Esc releases</div>
        )}
        {error && <div className="explorer-empty">{error}</div>}
        {!loading && !error && map?.points.length === 0 && (
          <div className="explorer-empty">No embedded essays yet. Run an embedding batch, then refresh this map.</div>
        )}

        {selected && (
          <aside className="explorer-panel">
            <div className="document-meta">
              <span>{selected.document.source_domain}</span>
              <span>{selected.document.document_type}</span>
              {selected.cluster_id != null && <span>cluster {selected.cluster_id}</span>}
            </div>
            <h2>{selected.document.title || selected.document.url}</h2>
            {selected.document.summary && <p>{selected.document.summary}</p>}
            <div className="topics">
              {selected.document.topics.slice(0, 6).map((topic) => <span key={topic}>{topic}</span>)}
            </div>
            <div className="embedding-neighborhood">
              <div>
                <strong>Nearest by full embedding</strong>
                <span>Computed from original vectors, not the compressed 3D map.</span>
              </div>
              {neighborsLoading && <small>Loading true nearest neighbors...</small>}
              {!neighborsLoading && neighbors.map((neighbor) => (
                <button
                  key={neighbor.document.id}
                  type="button"
                  onClick={() => {
                    const point = map?.points.find((item) => item.document.id === neighbor.document.id);
                    if (point) selectPoint(point);
                  }}
                >
                  <span>{neighbor.document.title || neighbor.document.url}</span>
                  <small>
                    {neighbor.document.source_domain} · cosine {(neighbor.similarity * 100).toFixed(1)}%
                  </small>
                </button>
              ))}
            </div>
            <a href={selected.document.url}>
              <ArrowUpRight size={16} />
              Open
            </a>
          </aside>
        )}
      </div>

      <div className="explorer-bottom-dock">
        <div className="explorer-controls">
          <span className={flightActive ? 'active' : ''}>
            <MousePointer2 size={15} />
            {flightActive ? 'Flying' : 'Click canvas'}
          </span>
          <span><kbd>W</kbd><kbd>A</kbd><kbd>S</kbd><kbd>D</kbd> Move</span>
          <span><kbd>Space</kbd><kbd>Ctrl</kbd> Up/down</span>
          <span><kbd>Shift</kbd> Boost</span>
        </div>
        <button className="explorer-help" type="button" onClick={() => setShowHelp((current) => !current)}>
          <HelpCircle size={16} />
          Help
        </button>
      </div>
      {showHelp && (
        <div className="explorer-help-card">
          <strong>Controls</strong>
          <span>Click the scene to capture the mouse. Press Esc to release it.</span>
          <span>Use WASD to fly, Space/Control to move vertically, Shift to boost, and scroll for quick forward/back movement.</span>
          <span>Paste an exact URL to teleport to its document.</span>
        </div>
      )}
    </section>
  );
}

function normalizeUrlForLookup(value: string) {
  const trimmed = value.trim();
  if (!trimmed) return '';
  const withScheme = /^[a-z][a-z0-9+.-]*:/i.test(trimmed) ? trimmed : `https://${trimmed}`;
  try {
    const parsed = new URL(withScheme);
    parsed.protocol = parsed.protocol.toLowerCase();
    parsed.hostname = parsed.hostname.toLowerCase().replace(/^www\./, '');
    if (parsed.pathname !== '/' && parsed.pathname.endsWith('/')) {
      parsed.pathname = parsed.pathname.slice(0, -1);
    }
    parsed.hash = '';
    const query = new URLSearchParams();
    Array.from(parsed.searchParams.entries())
      .filter(([key]) => {
        const lowered = key.toLowerCase();
        return !TRACKING_KEYS.has(lowered) && !lowered.startsWith('utm_');
      })
      .sort(([left], [right]) => left.localeCompare(right))
      .forEach(([key, item]) => query.append(key, item));
    parsed.search = query.toString();
    return parsed.toString();
  } catch {
    return trimmed.toLowerCase();
  }
}
