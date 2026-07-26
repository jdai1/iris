import type { SourceProfileAnalysis, SourceProfileLink } from '../types';
import { Chip, ChipList, StateMessage } from './ui';

export function ProfileAnalysisCard({ analysis }: { analysis: SourceProfileAnalysis | null }) {
  const facts = analysis?.scraped_facts;
  const themes = analysis?.themes?.length ? analysis.themes : facts?.top_topics?.slice(0, 12).map((item) => item.topic) ?? [];
  const links = analysis?.public_links?.length ? analysis.public_links : facts?.public_links ?? [];
  const contact = analysis?.public_contact?.length ? analysis.public_contact : facts?.public_contact ?? [];

  if (!analysis) {
    return (
      <div className="profile-analysis-card grid gap-4">
        <StateMessage className="profile-empty">No profile analysis yet.</StateMessage>
      </div>
    );
  }

  return (
    <div className="profile-analysis-card grid gap-4">
      {analysis.bio && <p className="profile-bio leading-relaxed text-[var(--text)]">{analysis.bio}</p>}
      <ProfileChipSection title="Audience" items={analysis.audiences ?? []} />
      <ProfileChipSection title="Writes about" items={themes} />
      <ProfileTakeSection takes={analysis.strong_takes ?? []} />
      <ProfileLinkSection title="Links" links={links} />
      <ProfileLinkSection title="Contact" links={contact} />
      {analysis.caveats && analysis.caveats.length > 0 && (
        <div className="profile-caveats text-[var(--text-muted)]">
          {analysis.caveats.map((caveat) => <p key={caveat}>{caveat}</p>)}
        </div>
      )}
    </div>
  );
}

function ProfileChipSection({ title, items }: { title: string; items: string[] }) {
  if (!items.length) return null;
  return (
    <section className="profile-analysis-section grid gap-2">
      <h4 className="text-sm font-semibold text-[var(--text)]">{title}</h4>
      <ChipList className="profile-chip-list">
        {items.map((item) => <Chip key={item}>{item}</Chip>)}
      </ChipList>
    </section>
  );
}

function ProfileTakeSection({ takes }: { takes: Array<{ take: string }> }) {
  if (!takes.length) return null;
  return (
    <section className="profile-analysis-section grid gap-2">
      <h4 className="text-sm font-semibold text-[var(--text)]">Opinions</h4>
      <ul className="profile-take-list m-0 pl-4 text-[var(--text)]">
        {takes.map((item) => <li key={item.take}>{item.take}</li>)}
      </ul>
    </section>
  );
}

function ProfileLinkSection({ title, links }: { title: string; links: SourceProfileLink[] }) {
  const usable = links.filter((link) => link.url);
  if (!usable.length) return null;
  return (
    <section className="profile-analysis-section grid gap-2">
      <h4 className="text-sm font-semibold text-[var(--text)]">{title}</h4>
      <div className="profile-link-list grid gap-1">
        {usable.map((link) => (
          <a key={link.url} href={link.url} target="_blank" rel="noreferrer" className="font-semibold text-[var(--text)] no-underline">
            {link.label || link.kind || link.url}
          </a>
        ))}
      </div>
    </section>
  );
}
