import { StrictMode, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Box, Button, Flex, Heading, Text } from '@chakra-ui/react';
import { ExternalLink, LogOut } from 'lucide-react';
import { getAuthToken, irisRequest, openIris } from './chrome';
import { IrisProvider } from './system';

type IrisUser = { email?: string | null; display_name?: string | null };

function App() {
  const [state, setState] = useState<'checking' | 'signed-out' | 'signed-in' | 'expired'>('checking');
  const [user, setUser] = useState<IrisUser | null>(null);
  const check = async () => {
    if (!await getAuthToken()) { setState('signed-out'); setUser(null); return; }
    try { setUser(await irisRequest<IrisUser>('/api/me')); setState('signed-in'); }
    catch { setState('expired'); setUser(null); }
  };
  useEffect(() => { check(); const listener = () => check(); chrome.storage.onChanged.addListener(listener); return () => chrome.storage.onChanged.removeListener(listener); }, []);
  async function disconnect() {
    await Promise.all([chrome.storage.local.remove('authToken'), chrome.storage.sync.set({ onboardingComplete: false })]);
    setState('signed-out'); setUser(null);
  }
  const signedIn = state === 'signed-in';
  return <Box width="min(720px, calc(100% - 48px))" mx="auto" py="76px">
    <Box className="iris-brand" mb="72px">iris</Box>
    <Text color="iris.500" fontSize="11px" fontWeight="650" letterSpacing=".08em" textTransform="uppercase">Browser extension</Text>
    <Heading mt="3" fontSize="clamp(34px, 6vw, 58px)" fontWeight="520" letterSpacing="-.055em" lineHeight=".98">{signedIn ? 'Connected.' : 'Connect Iris.'}</Heading>
    <Text mt="5" color="iris.500" fontSize="15px" lineHeight="1.6">{signedIn ? 'Pages, notes, and highlights save to the same Iris account you use on the web.' : 'Sign in to save pages and highlights to your Iris bookshelf.'}</Text>
    <Box mt="10" borderTop="1px solid" borderColor="iris.200">
      <Flex py="5" align="center" justify="space-between" borderBottom="1px solid" borderColor="iris.200">
        <Box><Text fontSize="13px" fontWeight="600">Account</Text><Text mt="1" color={signedIn ? '#2e6b3f' : 'iris.500'} fontSize="12px">{signedIn ? user?.email || user?.display_name || 'Signed in to Iris' : state === 'checking' ? 'Checking…' : state === 'expired' ? 'Session expired' : 'Not signed in'}</Text></Box>
        {signedIn ? <Button size="sm" variant="ghost" borderRadius="0" color="iris.500" onClick={disconnect}><LogOut size={14}/>Disconnect</Button> : <Button size="sm" borderRadius="0" bg="iris.900" color="white" onClick={() => openIris(true)}>Sign in →</Button>}
      </Flex>
      <Flex py="5" align="center" justify="space-between" borderBottom="1px solid" borderColor="iris.200">
        <Box><Text fontSize="13px" fontWeight="600">Iris bookshelf</Text><Text mt="1" color="iris.500" fontSize="12px">Open your saved pages, notes, and highlights.</Text></Box>
        <Button size="sm" variant="outline" borderRadius="0" onClick={() => openIris()}>Open Iris <ExternalLink size={14}/></Button>
      </Flex>
      <Flex py="5" align="center" justify="space-between">
        <Box><Text fontSize="13px" fontWeight="600">How it works</Text><Text mt="1" color="iris.500" fontSize="12px">Review the save and highlight workflow.</Text></Box>
        <Button size="sm" variant="outline" borderRadius="0" onClick={() => chrome.tabs.create({ url: chrome.runtime.getURL('onboarding.html') })}>View guide</Button>
      </Flex>
    </Box>
  </Box>;
}
createRoot(document.getElementById('root')!).render(<StrictMode><IrisProvider><App/></IrisProvider></StrictMode>);
