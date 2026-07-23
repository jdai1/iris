import type { ReactNode } from 'react';
import { ChakraProvider, createSystem, defaultConfig, defineConfig } from '@chakra-ui/react';
import './ui.css';

const config = defineConfig({
  globalCss: {
    'html, body, #root': { minHeight: '100%', margin: '0' },
    body: {
      bg: '#ffffff', color: '#111111',
      fontFamily: 'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    },
    '*': { boxSizing: 'border-box' },
  },
  theme: { tokens: {
    fonts: {
      heading: { value: 'Inter, ui-sans-serif, system-ui, sans-serif' },
      body: { value: 'Inter, ui-sans-serif, system-ui, sans-serif' },
    },
    colors: { iris: {
      50: { value: '#ffffff' }, 100: { value: '#f7f7f5' }, 200: { value: '#ececea' },
      300: { value: '#d8d8d4' }, 500: { value: '#767676' }, 700: { value: '#2f2f2f' }, 900: { value: '#111111' },
    } },
  } },
});

const system = createSystem(defaultConfig, config);
export function IrisProvider({ children }: { children: ReactNode }) {
  return <ChakraProvider value={system}>{children}</ChakraProvider>;
}
