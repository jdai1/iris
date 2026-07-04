import { useEffect, useState } from 'react';
import { Badge, Box, Heading, HStack, Link, Text } from '@chakra-ui/react';
import { ArrowUpRight, ChevronRight, MoreHorizontal } from 'lucide-react';
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
  const [saved, setSaved] = useState(document.bookshelf_status === 'saved');
  const [favorited, setFavorited] = useState(Boolean(document.bookshelf_favorited));
  const [addedCollectionIds, setAddedCollectionIds] = useState<Set<number>>(new Set());
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setSaved(document.bookshelf_status === 'saved');
    setFavorited(Boolean(document.bookshelf_favorited));
  }, [document.id, document.bookshelf_status, document.bookshelf_favorited]);

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
      setActionsOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save');
    } finally {
      setSaving(false);
    }
  }

  async function toggleFavorite() {
    setSaving(true);
    setError(null);
    try {
      const nextFavorited = !favorited;
      await updateDocumentBookshelf(document.id, { favorited: nextFavorited });
      setFavorited(nextFavorited);
      setActionsOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not update favorite');
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
      setActionsOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not add');
    } finally {
      setSaving(false);
    }
  }

  const actionsMenu = (
    <div className="document-actions-menu">
      <button
        className="document-actions-trigger"
        type="button"
        onClick={() => {
          const nextOpen = !actionsOpen;
          setActionsOpen(nextOpen);
          if (nextOpen) loadCollections();
        }}
        aria-label="Document actions"
        aria-expanded={actionsOpen}
        data-tooltip="Actions"
      >
        <MoreHorizontal size={17} />
      </button>
      {actionsOpen && (
        <div className="document-actions-popover">
          <button type="button" onClick={saveToReadNext} disabled={saving}>
            {saved ? 'In read next' : 'Read next'}
          </button>
          <button type="button" onClick={toggleFavorite} disabled={saving}>
            {favorited ? 'Favorited' : 'Favorite'}
          </button>
          <div className="document-actions-submenu" onMouseEnter={loadCollections} onFocus={loadCollections}>
            <button type="button" disabled={saving}>
              <span>Add to collection</span>
              <ChevronRight size={14} />
            </button>
            <div className="document-actions-submenu-list">
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
          </div>
        </div>
      )}
    </div>
  );

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
          {compact && (
            <Link href={document.url} className="document-open-icon" color="iris.900" fontWeight="650" textDecoration="none" aria-label="Open document" data-tooltip="Open document">
              <ArrowUpRight size={16} />
            </Link>
          )}
        </Heading>
        {compact && actionsMenu}
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
      {(!compact || error) && (
        <div className="document-bookshelf-actions">
          {!compact && actionsMenu}
          {error && <small>{error}</small>}
        </div>
      )}
    </Box>
  );
}
