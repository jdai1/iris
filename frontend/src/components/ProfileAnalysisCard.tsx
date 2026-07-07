import { Box, Link, Text } from '@chakra-ui/react';
import type { SourceProfileAnalysis, SourceProfileLink } from '../types';
import { Chip, ChipList, Panel, StateMessage } from './ui';

export function ProfileAnalysisCard({ analysis }: { analysis: SourceProfileAnalysis | null }) {
  const facts = analysis?.scraped_facts;
  const themes = analysis?.themes?.length ? analysis.themes : facts?.top_topics?.slice(0, 12).map((item) => item.topic) ?? [];
  const links = analysis?.public_links?.length ? analysis.public_links : facts?.public_links ?? [];
  const contact = analysis?.public_contact?.length ? analysis.public_contact : facts?.public_contact ?? [];

  if (!analysis) {
    return (
      <Panel className="profile-analysis-card" p="4">
        <ProfileUnavailable labels={['bio', 'themes', 'writing style', 'strong takes', 'links', 'contact']} />
      </Panel>
    );
  }

  return (
    <Panel className="profile-analysis-card" p="4" display="grid" gap="4">
      {analysis.bio ? <Text className="profile-bio" color="fg.default" lineHeight="1.6">{analysis.bio}</Text> : <ProfileUnavailable labels={['bio']} />}
      <ProfileChipSection title="Writes about" items={themes} />
      <ProfileChipSection title="Style" items={analysis.writing_style ?? []} />
      <ProfileTakeSection takes={analysis.strong_takes ?? []} />
      <ProfileLinkSection title="Links" links={links} />
      <ProfileLinkSection title="Contact" links={contact} />
      {analysis.caveats && analysis.caveats.length > 0 && (
        <ChipList className="profile-caveats">
          {analysis.caveats.map((caveat) => <Chip key={caveat}>{caveat}</Chip>)}
        </ChipList>
      )}
    </Panel>
  );
}

function ProfileChipSection({ title, items }: { title: string; items: string[] }) {
  if (!items.length) return <ProfileUnavailable labels={[title.toLowerCase()]} />;
  return (
    <Box className="profile-analysis-section" display="grid" gap="2">
      <Text as="h4" color="fg.default" fontSize="sm" fontWeight="600">{title}</Text>
      <ChipList className="profile-chip-list">
        {items.map((item) => <Chip key={item}>{item}</Chip>)}
      </ChipList>
    </Box>
  );
}

function ProfileTakeSection({ takes }: { takes: Array<{ take: string }> }) {
  if (!takes.length) return <ProfileUnavailable labels={['strong takes']} />;
  return (
    <Box className="profile-analysis-section" display="grid" gap="2">
      <Text as="h4" color="fg.default" fontSize="sm" fontWeight="600">Strong takes</Text>
      <Box as="ul" className="profile-take-list" m="0" pl="4" color="fg.default">
        {takes.map((item) => <li key={item.take}>{item.take}</li>)}
      </Box>
    </Box>
  );
}

function ProfileLinkSection({ title, links }: { title: string; links: SourceProfileLink[] }) {
  const usable = links.filter((link) => link.url);
  if (!usable.length) return <ProfileUnavailable labels={[title.toLowerCase()]} />;
  return (
    <Box className="profile-analysis-section" display="grid" gap="2">
      <Text as="h4" color="fg.default" fontSize="sm" fontWeight="600">{title}</Text>
      <Box className="profile-link-list" display="grid" gap="1">
        {usable.map((link) => (
          <Link key={link.url} href={link.url} target="_blank" rel="noreferrer" color="fg.default" fontWeight="600" textDecoration="none">
            {link.label || link.kind || link.url}
          </Link>
        ))}
      </Box>
    </Box>
  );
}

function ProfileUnavailable({ labels }: { labels: string[] }) {
  return (
    <StateMessage className="profile-unavailable">
      {labels.map((label) => <Text as="span" key={label}>{label} unavailable</Text>)}
    </StateMessage>
  );
}
