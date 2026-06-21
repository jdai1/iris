import type { SourceProfileAnalysis, SourceProfileLink } from '../types';

export function ProfileAnalysisCard({ analysis }: { analysis: SourceProfileAnalysis | null }) {
  const facts = analysis?.scraped_facts;
  const themes = analysis?.themes?.length ? analysis.themes : facts?.top_topics?.slice(0, 12).map((item) => item.topic) ?? [];
  const links = analysis?.public_links?.length ? analysis.public_links : facts?.public_links ?? [];
  const contact = analysis?.public_contact?.length ? analysis.public_contact : facts?.public_contact ?? [];

  if (!analysis) {
    return (
      <div className="profile-analysis-card">
        <ProfileUnavailable labels={['bio', 'themes', 'writing style', 'strong takes', 'links', 'contact']} />
      </div>
    );
  }

  return (
    <div className="profile-analysis-card">
      {analysis.bio ? <p className="profile-bio">{analysis.bio}</p> : <ProfileUnavailable labels={['bio']} />}
      <ProfileChipSection title="Writes about" items={themes} />
      <ProfileChipSection title="Style" items={analysis.writing_style ?? []} />
      <ProfileTakeSection takes={analysis.strong_takes ?? []} />
      <ProfileLinkSection title="Links" links={links} />
      <ProfileLinkSection title="Contact" links={contact} />
      {analysis.caveats && analysis.caveats.length > 0 && (
        <div className="profile-caveats">
          {analysis.caveats.map((caveat) => <span key={caveat}>{caveat}</span>)}
        </div>
      )}
    </div>
  );
}

function ProfileChipSection({ title, items }: { title: string; items: string[] }) {
  if (!items.length) return <ProfileUnavailable labels={[title.toLowerCase()]} />;
  return (
    <div className="profile-analysis-section">
      <h4>{title}</h4>
      <div className="profile-chip-list">
        {items.map((item) => <span key={item}>{item}</span>)}
      </div>
    </div>
  );
}

function ProfileTakeSection({ takes }: { takes: Array<{ take: string }> }) {
  if (!takes.length) return <ProfileUnavailable labels={['strong takes']} />;
  return (
    <div className="profile-analysis-section">
      <h4>Strong takes</h4>
      <ul className="profile-take-list">
        {takes.map((item) => <li key={item.take}>{item.take}</li>)}
      </ul>
    </div>
  );
}

function ProfileLinkSection({ title, links }: { title: string; links: SourceProfileLink[] }) {
  const usable = links.filter((link) => link.url);
  if (!usable.length) return <ProfileUnavailable labels={[title.toLowerCase()]} />;
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
