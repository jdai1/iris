import { Box, Link, Text } from '@chakra-ui/react';
import type { SourceProfileAnalysis, SourceProfileLink } from '../types';
import { Chip, ChipList, StateMessage } from './ui';

export function ProfileAnalysisCard({ analysis }: { analysis: SourceProfileAnalysis | null }) {
  const facts = analysis?.scraped_facts;
  const themes = analysis?.themes?.length ? analysis.themes : facts?.top_topics?.slice(0, 12).map((item) => item.topic) ?? [];
  const links = analysis?.public_links?.length ? analysis.public_links : facts?.public_links ?? [];
  const contact = analysis?.public_contact?.length ? analysis.public_contact : facts?.public_contact ?? [];

  if (!analysis) {
    return (
      <Box className="profile-analysis-card" display="grid" gap="4">
        <StateMessage className="profile-empty">Loading profile...</StateMessage>
      </Box>
    );
  }

  return (
    <Box className="profile-analysis-card" display="grid" gap="4">
      {analysis.bio && <Text className="profile-bio" color="fg.default" lineHeight="1.6">{analysis.bio}</Text>}
      <ProfileChipSection title="Writes about" items={themes} />
      <ProfileTakeSection takes={analysis.strong_takes ?? []} />
      <ProfileLinkSection title="Links" links={links} />
      <ProfileLinkSection title="Contact" links={contact} />
      {analysis.caveats && analysis.caveats.length > 0 && (
        <Box className="profile-caveats" color="fg.muted">
          {analysis.caveats.map((caveat) => <Text as="p" key={caveat}>{caveat}</Text>)}
        </Box>
      )}
    </Box>
  );
}

function ProfileChipSection({ title, items }: { title: string; items: string[] }) {
  if (!items.length) return null;
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
  if (!takes.length) return null;
  return (
    <Box className="profile-analysis-section" display="grid" gap="2">
      <Text as="h4" color="fg.default" fontSize="sm" fontWeight="600">Opinions</Text>
      <Box as="ul" className="profile-take-list" m="0" pl="4" color="fg.default">
        {takes.map((item) => <li key={item.take}>{item.take}</li>)}
      </Box>
    </Box>
  );
}

function ProfileLinkSection({ title, links }: { title: string; links: SourceProfileLink[] }) {
  const usable = links.filter((link) => link.url);
  if (!usable.length) return null;
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
