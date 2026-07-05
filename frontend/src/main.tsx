import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { ChakraProvider, createSystem, defaultConfig, defineConfig } from '@chakra-ui/react';
import { Box } from '@chakra-ui/react';
import App from './App';
import { EvalResultsView } from './EvalResultsView';
import './index.css';

const config = defineConfig({
  globalCss: {
    body: {
      bg: '#ffffff',
      color: '#111111',
      fontFamily:
        'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    },
  },
  theme: {
    tokens: {
      fonts: {
        heading: { value: 'Inter, ui-sans-serif, system-ui, sans-serif' },
        body: { value: 'Inter, ui-sans-serif, system-ui, sans-serif' },
      },
      colors: {
        iris: {
          50: { value: '#ffffff' },
          100: { value: '#f7f7f5' },
          200: { value: '#ececea' },
          300: { value: '#d8d8d4' },
          500: { value: '#767676' },
          700: { value: '#2f2f2f' },
          900: { value: '#111111' },
        },
      },
    },
  },
});

const system = createSystem(defaultConfig, config);

function Root() {
  const pathname = window.location.pathname.replace(/\/+$/, '') || '/';
  if (pathname === '/dev/evals' || pathname === '/evals') {
    return (
      <Box as="main" className="eval-dev-shell">
        <EvalResultsView />
      </Box>
    );
  }
  return <App />;
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ChakraProvider value={system}>
      <Root />
    </ChakraProvider>
  </StrictMode>,
);
