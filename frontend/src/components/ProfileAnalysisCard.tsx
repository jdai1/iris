import type { SourceProfileAnalysis } from '../types';

export function ProfileAnalysisCard({ analysis }: { analysis: SourceProfileAnalysis | null }) {
  const payload = analysis?.payload;
  const facts = analysis?.scraped_facts;
  const themes = payload?.themes?.length ? payload.themes : facts?.top_topics?.slice(0, 12).map((item) => item.topic) ?? [];
  const links = payload?.public_links?.length ? payload.public_links : facts?.public_links ?? [];
  const contact = payload?.public_contact?.length ? payload.public_contact : facts?.public_contact ?? [];
  const unavailable = new Set(analysis?.unavailable_sections ?? payload?.unavailable_sections ?? []);

  if (!analysis) {
    return (
      <div className="profile-analysis-card">
        <ProfileUnavailable labels={['bio', 'themes', 'writing style', 'strong takes', 'links', 'contact']} />
      </div>
    );
  }

  return (
    <div className="profile-analysis-card">
      {payload?.bio ? <p className="profile-bio">{payload.bio}</p> : <ProfileUnavailable labels={['bio']} />}
      <ProfileChipSection title="Writes about" items={themes} unavailable={unavailable.has('themes')} />
      <ProfileChipSection title="Style" items={payload?.writing_style ?? []} unavailable={unavailable.has('writing_style')} />
      <ProfileTakeSection takes={payload?.strong_takes ?? []} unavailable={unavailable.has('strong_takes')} />
      <ProfileLinkSection title="Links" links={links} unavailable={unavailable.has('public_links')} />
      <ProfileLinkSection title="Contact" links={contact} unavailable={unavailable.has('public_contact')} />
      {payload?.caveats && payload.caveats.length > 0 && (
        <div className="profile-caveats">
          {payload.caveats.map((caveat) => <span key={caveat}>{caveat}</span>)}
        </div>
      )}
    </div>
  );
}

function ProfileChipSection({ title, items, unavailable }: { title: string; items: string[]; unavailable: boolean }) {
  if (!items.length) return unavailable ? <ProfileUnavailable labels={[title.toLowerCase()]} /> : null;
  return (
    <div className="profile-analysis-section">
      <h4>{title}</h4>
      <div className="profile-chip-list">
        {items.map((item) => <span key={item}>{item}</span>)}
      </div>
    </div>
  );
}

function ProfileTakeSection({ takes, unavailable }: { takes: Array<{ take: string }>; unavailable: boolean }) {
  if (!takes.length) return unavailable ? <ProfileUnavailable labels={['strong takes']} /> : null;
  return (
    <div className="profile-analysis-section">
      <h4>Strong takes</h4>
      <ul className="profile-take-list">
        {takes.map((item) => <li key={item.take}>{item.take}</li>)}
      </ul>
    </div>
  );
}

function ProfileLinkSection({ title, links, unavailable }: { title: string; links: Array<{ label?: string; url?: string; kind?: string }>; unavailable: boolean }) {
  const usable = links.filter((link) => link.url);
  if (!usable.length) return unavailable ? <ProfileUnavailable labels={[title.toLowerCase()]} /> : null;
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
