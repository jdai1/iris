import { lazy, Suspense } from 'react';
import { GitFork, List, Orbit } from 'lucide-react';
import type { DirectoryMode, ProfileTarget } from '../app/navigation';
import { GraphExplorer } from '../GraphExplorer';
import { DirectoryView } from './DirectoryView';

const EmbeddingExplorer = lazy(() =>
  import('../EmbeddingExplorer').then((module) => ({ default: module.EmbeddingExplorer })),
);

export function DirectoryHub({
  mode,
  target,
  onModeChange,
  onOpenProfile,
  onDirectoryRoot,
}: {
  mode: DirectoryMode;
  target: ProfileTarget;
  onModeChange: (mode: DirectoryMode) => void;
  onOpenProfile: (sourceId: number, domain: string) => void;
  onDirectoryRoot: () => void;
}) {
  const modes: Array<{ value: DirectoryMode; label: string; icon: typeof List }> = [
    { value: 'sources', label: 'Sources', icon: List },
    { value: 'explore', label: 'Explore', icon: Orbit },
    { value: 'graph', label: 'Graph', icon: GitFork },
  ];
  return (
    <section className="directory-hub">
      <div className="directory-mode-tabs" role="tablist" aria-label="Directory views">
        {modes.map((item) => {
          const Icon = item.icon;
          return (
            <button
              key={item.value}
              type="button"
              role="tab"
              aria-selected={mode === item.value}
              className={mode === item.value ? 'directory-mode-tab directory-mode-tab-active' : 'directory-mode-tab'}
              onClick={() => onModeChange(item.value)}
            >
              <Icon size={14} />
              {item.label}
            </button>
          );
        })}
      </div>
      <div className={mode === 'sources' ? 'directory-mode-content' : 'directory-mode-content directory-mode-content-visual'}>
        {mode === 'sources' && (
          <DirectoryView
            target={target}
            onOpenProfile={onOpenProfile}
            onDirectoryRoot={onDirectoryRoot}
          />
        )}
        {mode === 'explore' && (
          <Suspense fallback={null}>
            <EmbeddingExplorer />
          </Suspense>
        )}
        {mode === 'graph' && (
          <GraphExplorer
            onOpenProfile={onOpenProfile}
            initialDomain={target?.domain}
          />
        )}
      </div>
    </section>
  );
}
