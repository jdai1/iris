import { Badge, Box, Heading, HStack, Link, Text } from '@chakra-ui/react';
import { ArrowUpRight } from 'lucide-react';
import type { Document } from '../types';

type DocumentCardProps = {
  document: Document;
  reason: string;
  score?: number;
  onOpenProfile?: (sourceId: number, domain: string) => void;
  compact?: boolean;
};

export function DocumentCard({
  document,
  reason,
  score,
  onOpenProfile,
  compact = false,
}: DocumentCardProps) {
  return (
    <Box as="article" className={compact ? 'document-card document-card-compact' : 'document-card'}>
      {!compact && (
        <HStack gap="2" flexWrap="wrap" color="iris.500" fontSize="xs" textTransform="uppercase">
          <button className="profile-link" type="button" onClick={() => onOpenProfile?.(document.source_id, document.source_domain)}>
            {document.source_domain}
          </button>
          <Text as="span">{document.document_type}</Text>
          {typeof score === 'number' && <Text as="span">{score.toFixed(2)}</Text>}
        </HStack>
      )}
      <div className={compact ? 'document-title-row' : undefined}>
        <Heading as="h3" mt="2" mb="3" fontSize="xl" lineHeight="1.2" fontWeight="650">
          {document.title ?? document.url}
        </Heading>
        {compact && (
          <Link href={document.url} className="document-open-icon" color="iris.900" fontWeight="650" textDecoration="none" aria-label="Open document">
            <ArrowUpRight size={16} />
          </Link>
        )}
      </div>
      {document.summary && <Text color="iris.700" lineHeight="1.6" mb="3">{document.summary}</Text>}
      {!compact && <Text color="iris.500" fontSize="sm" lineHeight="1.55" mb="4">{reason}</Text>}
      <HStack className="topics" gap="1.5" flexWrap="wrap" mb="4">
        {document.topics.slice(0, 6).map((topic) => (
          <Badge key={topic} variant="outline" borderColor="iris.300" color="iris.700" bg="iris.100" fontWeight="500">
            {topic}
          </Badge>
        ))}
      </HStack>
      {!compact && (
        <HStack>
          <Link href={document.url} color="iris.900" fontWeight="650" textDecoration="none">
            <ArrowUpRight size={16} />
            Open
          </Link>
        </HStack>
      )}
    </Box>
  );
}
