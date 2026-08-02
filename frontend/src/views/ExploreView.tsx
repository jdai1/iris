import { lazy, Suspense } from 'react';

const EmbeddingExplorer = lazy(() =>
  import('../EmbeddingExplorer').then((module) => ({ default: module.EmbeddingExplorer })),
);

export function ExploreView() {
  return (
    <section className="min-h-svh min-w-0 overflow-hidden" aria-label="Explore documents">
      <Suspense fallback={<ExploreSkeleton />}>
        <EmbeddingExplorer />
      </Suspense>
    </section>
  );
}

function ExploreSkeleton() {
  return (
    <div className="grid min-h-svh place-items-center" aria-label="Loading Explore">
      <span className="size-10 animate-pulse rounded-full bg-muted" />
    </div>
  );
}
