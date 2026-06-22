import { useState } from 'react';
import { Badge, Box, Heading, HStack, Link, Text } from '@chakra-ui/react';
import { ArrowUpRight, BookmarkPlus, Plus } from 'lucide-react';
import { addBookshelfCollectionItem, getBookshelfCollections, updateDocumentBookshelf } from '../api';
import type { BookshelfCollection, Document } from '../types';

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
  const [collections, setCollections] = useState<BookshelfCollection[]>([]);
  const [collectionsLoaded, setCollectionsLoaded] = useState(false);
  const [actionsOpen, setActionsOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [addedCollectionIds, setAddedCollectionIds] = useState<Set<number>>(new Set());
  const [error, setError] = useState<string | null>(null);

  async function loadCollections() {
    if (collectionsLoaded) return;
    try {
      setCollections(await getBookshelfCollections());
      setCollectionsLoaded(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load collections');
    }
  }

  async function saveToReadNext() {
    setSaving(true);
    setError(null);
    try {
      await updateDocumentBookshelf(document.id, { status: 'saved' });
      setSaved(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save');
    } finally {
      setSaving(false);
    }
  }

  async function addToCollection(collectionId: number) {
    setSaving(true);
    setError(null);
    try {
      await addBookshelfCollectionItem(collectionId, document.id);
      setAddedCollectionIds((current) => new Set(current).add(collectionId));
      setSaved(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not add');
    } finally {
      setSaving(false);
    }
  }

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
      {compact && (
        <button className="document-compact-domain" type="button" onClick={() => onOpenProfile?.(document.source_id, document.source_domain)}>
          {document.source_domain}
        </button>
      )}
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
      <div className="document-bookshelf-actions">
        <button type="button" onClick={saveToReadNext} disabled={saving || saved}>
          <BookmarkPlus size={14} />
          {saved ? 'Saved' : 'Read next'}
        </button>
        <div className="document-collection-menu">
          <button
            type="button"
            onClick={() => {
              const nextOpen = !actionsOpen;
              setActionsOpen(nextOpen);
              if (nextOpen) loadCollections();
            }}
            aria-expanded={actionsOpen}
          >
            <Plus size={14} />
            Collection
          </button>
          {actionsOpen && (
            <div className="document-collection-menu-list">
              {collections.length === 0 && <span>No collections yet</span>}
              {collections.map((collection) => {
                const added = addedCollectionIds.has(collection.id);
                return (
                  <button key={collection.id} type="button" onClick={() => addToCollection(collection.id)} disabled={saving || added}>
                    {added ? 'Added' : collection.name}
                  </button>
                );
              })}
            </div>
          )}
        </div>
        {error && <small>{error}</small>}
      </div>
    </Box>
  );
}
