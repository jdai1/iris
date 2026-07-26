import type { ProfileTarget } from '../app/navigation';
import { DirectoryView } from './DirectoryView';

export function DirectoryHub({
  target,
  onOpenProfile,
  onDirectoryRoot,
}: {
  target: ProfileTarget;
  onOpenProfile: (sourceId: number, domain: string) => void;
  onDirectoryRoot: () => void;
}) {
  return (
    <section className="min-h-svh min-w-0">
      <DirectoryView
        target={target}
        onOpenProfile={onOpenProfile}
        onDirectoryRoot={onDirectoryRoot}
      />
    </section>
  );
}
