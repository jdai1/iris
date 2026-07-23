import { StrictMode, useCallback, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Box, Button, Flex, Heading, IconButton, Input, Spinner, Text, Textarea } from '@chakra-ui/react';
import { Check, Clock3, ExternalLink, Heart, MessageSquarePlus, Plus, RotateCw, Settings, X } from 'lucide-react';
import { Entry, getAuthToken, irisRequest, openIris } from './chrome';
import { IrisProvider } from './system';

type Capture = { entry: Entry };
type Phase = 'checking' | 'signed-out' | 'saving' | 'saved' | 'error';

function App() {
  const [phase, setPhase] = useState<Phase>('checking');
  const [entry, setEntry] = useState<Entry | null>(null);
  const [domain, setDomain] = useState('');
  const [noteOpen, setNoteOpen] = useState(false);
  const [note, setNote] = useState('');
  const [topic, setTopic] = useState('');
  const [message, setMessage] = useState('');
  const [messageError, setMessageError] = useState(false);
  const [updating, setUpdating] = useState(false);

  const capture = useCallback(async () => {
    setMessage(''); setMessageError(false); setEntry(null);
    if (!await getAuthToken()) { setPhase('signed-out'); return; }
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id || !tab.url || !/^https?:\/\//i.test(tab.url)) {
      setPhase('error'); setMessage('Iris can only save regular web pages.'); return;
    }
    setDomain(new URL(tab.url).hostname.replace(/^www\./, ''));
    setPhase('saving');
    try {
      const page = await irisRequest<Capture>('/api/browser/pages/capture', {
        method: 'POST', body: JSON.stringify({ url: tab.url, title: tab.title || null, crawl_now: false }),
      });
      setEntry(page.entry); setNote(page.entry.note || page.entry.intent_note || ''); setPhase('saved');
      const stored = await chrome.storage.local.get({ savedUrls: [] });
      const savedUrls = [...new Set([...(stored.savedUrls as string[]), tab.url, page.entry.document.url])].slice(-2000);
      await chrome.storage.local.set({ savedUrls });
      chrome.tabs.sendMessage(tab.id, { type: 'iris-page-saved', page }).catch(() => undefined);
    } catch (error) {
      if (!await getAuthToken()) { setPhase('signed-out'); return; }
      setPhase('error'); setMessage(error instanceof Error ? error.message : 'Iris could not save this page.');
    }
  }, []);

  useEffect(() => {
    capture();
  }, [capture]);

  async function update(payload: Record<string, unknown>, success = 'Saved') {
    if (!entry || updating) return;
    setUpdating(true); setMessage(''); setMessageError(false);
    try {
      const updated = await irisRequest<Entry>(`/api/documents/${entry.document.id}/bookshelf`, { method: 'PATCH', body: JSON.stringify(payload) });
      setEntry(updated); setNote(updated.note || updated.intent_note || ''); setMessage(success);
      window.setTimeout(() => setMessage((current) => current === success ? '' : current), 1400);
      return true;
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Could not update this page.'); setMessageError(true); return false; }
    finally { setUpdating(false); }
  }

  const actionStyle = { borderRadius: '0', borderColor: 'iris.200', bg: 'white', color: 'iris.700', _hover: { bg: 'iris.100' } };
  return <Box minH="270px" p="20px 22px 16px">
    <Flex justify="space-between" align="center">
      <Box className="iris-brand">iris</Box>
      <Flex gap="1">
        <Button h="30px" px="2" variant="ghost" color="iris.500" fontSize="11px" borderRadius="0" onClick={() => openIris()}>Open Iris <ExternalLink size={13}/></Button>
        <IconButton aria-label="Extension settings" title="Extension settings" variant="ghost" size="xs" borderRadius="0" color="iris.500" onClick={() => chrome.runtime.openOptionsPage()}><Settings size={15}/></IconButton>
      </Flex>
    </Flex>

    {(phase === 'checking' || phase === 'saving') && <Flex minH="185px" direction="column" justify="center" align="center" gap="3">
      <Spinner size="sm" borderWidth="1.5px" color="iris.900"/><Text color="iris.500" fontSize="12px">{phase === 'saving' ? 'Saving this page…' : 'Checking your session…'}</Text>
    </Flex>}

    {phase === 'signed-out' && <Box pt="10" pb="5">
      <Heading fontSize="24px" fontWeight="620" letterSpacing="-.035em">Save the good web.</Heading>
      <Text mt="2" mb="6" color="iris.500" fontSize="13px" lineHeight="1.55">Sign in once to sync saved pages, highlights, and notes with Iris.</Text>
      <Button bg="iris.900" color="white" borderRadius="0" size="sm" onClick={() => openIris(true)}>Sign in to Iris →</Button>
    </Box>}

    {phase === 'error' && <Box pt="10" pb="4">
      <Heading fontSize="20px" fontWeight="620">Couldn’t save this page</Heading>
      <Text mt="2" color="#a12d24" fontSize="12px" lineHeight="1.5">{message}</Text>
      <Flex mt="5" gap="2"><Button size="sm" borderRadius="0" bg="iris.900" color="white" onClick={capture}><RotateCw size={14}/>Try again</Button><Button size="sm" variant="outline" borderRadius="0" onClick={() => openIris()}>Open Iris</Button></Flex>
    </Box>}

    {phase === 'saved' && entry && <Box>
      <Flex mt="6" align="center" gap="2"><Box w="7px" h="7px" bg="#2e6b3f"/><Text color="#2e6b3f" fontSize="11px" fontWeight="650">Saved</Text><Text color="iris.300">·</Text><Text color="iris.500" fontSize="11px">{domain}</Text></Flex>
      <Heading mt="2" mb="5" fontSize="20px" lineHeight="1.25" fontWeight="590" letterSpacing="-.025em" maxH="50px" overflow="hidden">{entry.document.title || entry.document.url}</Heading>
      <Flex gap="2" pb="5" borderBottom="1px solid" borderColor="iris.200">
        <Button size="xs" variant="outline" {...actionStyle} bg={entry.favorited ? 'iris.100' : 'white'} color={entry.favorited ? 'iris.900' : 'iris.700'} disabled={updating} onClick={() => update({ favorited: !entry.favorited }, entry.favorited ? 'Removed from favorites' : 'Added to favorites')}><Heart size={14} fill={entry.favorited ? 'currentColor' : 'none'}/>{entry.favorited ? 'Favorited' : 'Favorite'}</Button>
        <Button size="xs" variant="outline" {...actionStyle} bg={entry.status === 'read' ? 'iris.100' : 'white'} disabled={updating} onClick={() => update({ status: entry.status === 'saved' ? 'read' : 'saved' }, entry.status === 'saved' ? 'Marked read' : 'Moved to Read next')}>{entry.status === 'saved' ? <Clock3 size={14}/> : <Check size={14}/>} {entry.status === 'saved' ? 'Read next' : 'Read'}</Button>
        <Button size="xs" variant="outline" {...actionStyle} disabled={updating} onClick={() => setNoteOpen((value) => !value)}><MessageSquarePlus size={14}/>{note ? 'Edit note' : 'Add note'}</Button>
      </Flex>

      {noteOpen && <Box py="4" borderBottom="1px solid" borderColor="iris.200">
        <Flex mb="2" justify="space-between"><Text color="iris.700" fontSize="11px" fontWeight="650">Note</Text><IconButton aria-label="Close note" variant="ghost" size="2xs" onClick={() => setNoteOpen(false)}><X size={13}/></IconButton></Flex>
        <Textarea value={note} onChange={(event) => setNote(event.target.value)} borderRadius="0" fontSize="13px" minH="84px" placeholder="Why is this worth keeping?"/>
        <Button mt="2" size="xs" borderRadius="0" bg="iris.900" color="white" disabled={updating} onClick={async () => { if (await update({ note: note.trim() || null }, 'Note saved')) setNoteOpen(false); }}>Save note</Button>
      </Box>}

      <Box pt="4">
        <Text mb="2" color="iris.700" fontSize="11px" fontWeight="650">Topics</Text>
        <Flex wrap="wrap" gap="2">{entry.tags.map((tag) => <Button key={tag} size="xs" borderRadius="0" bg="iris.100" color="iris.700" disabled={updating} onClick={() => update({ tags: entry.tags.filter((item) => item !== tag) }, `Removed ${tag}`)}>{tag}<X size={11}/></Button>)}</Flex>
        <form onSubmit={(event) => { event.preventDefault(); const value = topic.trim(); if (value && !entry.tags.includes(value)) { setTopic(''); update({ tags: [...entry.tags, value] }, `Added ${value}`); } }}>
          <Flex mt="2" align="center" borderBottom="1px solid" borderColor="iris.300"><Plus size={14} color="#767676"/><Input value={topic} onChange={(event) => setTopic(event.target.value)} px="2" border="0" outline="none" fontSize="13px" placeholder="Add a topic and press Enter"/></Flex>
        </form>
      </Box>
      <Flex mt="4" pt="3" borderTop="1px solid" borderColor="iris.100" justify="space-between" align="center"><Text color="iris.500" fontSize="11px">Select text on the page to highlight it.</Text><Text color={messageError ? '#a12d24' : '#2e6b3f'} fontSize="11px">{message}</Text></Flex>
    </Box>}
  </Box>;
}

createRoot(document.getElementById('root')!).render(<StrictMode><IrisProvider><App/></IrisProvider></StrictMode>);
