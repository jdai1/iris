import { StrictMode, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Box, Button, Flex, Heading, Text } from '@chakra-ui/react';
import { ExternalLink } from 'lucide-react';
import { getAuthToken, irisRequest, openIris } from './chrome';
import { IrisProvider } from './system';

function App() {
  const [state, setState] = useState<'checking' | 'signed-out' | 'ready'>('checking');
  const [status, setStatus] = useState('');
  const check = async () => {
    if (!await getAuthToken()) { setState('signed-out'); return; }
    try { await irisRequest('/api/me'); setState('ready'); setStatus(''); }
    catch { setState('signed-out'); setStatus('Your session expired. Sign in again.'); }
  };
  useEffect(() => {
    check();
    const listener = (changes: Record<string, chrome.storage.StorageChange>, area: string) => { if (area === 'local' && changes.authToken) check(); };
    chrome.storage.onChanged.addListener(listener); return () => chrome.storage.onChanged.removeListener(listener);
  }, []);

  return <Box minH="100vh" display="grid" alignItems="center" p="clamp(32px, 7vw, 112px)">
    <Box width="min(900px, 100%)">
      <Box className="iris-brand" mb="8">iris</Box>
      {state === 'checking' && <Text color="iris.500">Checking your Iris account…</Text>}
      {state === 'signed-out' && <>
        <Heading maxW="760px" fontSize="clamp(38px, 5.8vw, 76px)" fontWeight="660" letterSpacing="-.055em" lineHeight=".98">Save anything worth returning to.</Heading>
        <Text mt="5" maxW="520px" color="iris.500" fontSize="15px" lineHeight="1.6">One click saves the page. After that, select any passage to highlight it or add a comment.</Text>
        <Button mt="8" borderRadius="0" bg="iris.900" color="white" size="lg" onClick={() => openIris(true)}>Sign in to Iris →</Button>
        {status && <Text mt="3" color="#a12d24" fontSize="12px">{status}</Text>}
      </>}
      {state === 'ready' && <>
        <Heading fontSize="clamp(38px, 5.4vw, 70px)" fontWeight="660" letterSpacing="-.05em" lineHeight="1">Save first.<br/>Organize later.</Heading>
        <Flex mt="10" borderTop="1px solid" borderBottom="1px solid" borderColor="iris.200" direction={{ base: 'column', md: 'row' }}>
          {[
            ['01', 'Save', 'Click the Iris extension once. The current page is saved immediately.'],
            ['02', 'Highlight', 'Select text on the saved page, then choose Highlight or add a comment.'],
            ['03', 'Return', 'Find the page, note, and highlights together in your Iris bookshelf.'],
          ].map(([number, title, copy], index) => <Box key={number} flex="1" minH="185px" p="5" borderRight={{ base: '0', md: index < 2 ? '1px solid' : '0' }} borderBottom={{ base: index < 2 ? '1px solid' : '0', md: '0' }} borderColor="iris.200"><Text color="iris.300" fontSize="10px">{number}</Text><Heading mt="8" fontSize="17px">{title}</Heading><Text mt="2" color="iris.500" fontSize="12px" lineHeight="1.55">{copy}</Text></Box>)}
        </Flex>
        <Flex mt="8" gap="3"><Button borderRadius="0" bg="iris.900" color="white" onClick={() => openIris()}>Open Iris <ExternalLink size={15}/></Button><Button borderRadius="0" variant="outline" onClick={async () => { const [tab] = await chrome.tabs.query({ active: true, currentWindow: true }); if (tab?.id) chrome.tabs.remove(tab.id); }}>Got it</Button></Flex>
      </>}
    </Box>
  </Box>;
}
createRoot(document.getElementById('root')!).render(<StrictMode><IrisProvider><App/></IrisProvider></StrictMode>);
