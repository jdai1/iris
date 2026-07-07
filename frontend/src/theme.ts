import { createSystem, defaultConfig, defineConfig } from '@chakra-ui/react';

const config = defineConfig({
  globalCss: {
    body: {
      bg: 'var(--bg)',
      color: 'var(--text)',
      fontFamily: 'InterVariable, Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    },
  },
  theme: {
    semanticTokens: {
      colors: {
        bg: {
          canvas: { value: 'var(--bg)' },
          surface: { value: 'var(--bg-raised)' },
          subtle: { value: 'var(--bg-hover)' },
          muted: { value: 'var(--bg-sunken)' },
        },
        fg: {
          default: { value: 'var(--text)' },
          muted: { value: 'var(--text-muted)' },
          subtle: { value: 'var(--text-subtle)' },
        },
        border: {
          subtle: { value: 'var(--border-subtle)' },
          strong: { value: 'var(--border-input)' },
        },
        accent: {
          default: { value: 'var(--accent)' },
          muted: { value: 'var(--accent-hover)' },
        },
        danger: {
          default: { value: 'var(--status-red-text)' },
          subtle: { value: 'var(--status-red-bg)' },
          border: { value: 'var(--status-red-border)' },
        },
      },
    },
    tokens: {
      fonts: {
        heading: { value: 'InterVariable, Inter, ui-sans-serif, system-ui, sans-serif' },
        body: { value: 'InterVariable, Inter, ui-sans-serif, system-ui, sans-serif' },
      },
      colors: {
        iris: {
          50: { value: 'var(--bg)' },
          100: { value: 'var(--bg-sunken)' },
          200: { value: 'var(--border-subtle)' },
          300: { value: 'var(--border-input)' },
          500: { value: 'var(--text-subtle)' },
          700: { value: 'var(--text-secondary)' },
          900: { value: 'var(--text)' },
        },
      },
      radii: {
        ui: { value: '0' },
        compact: { value: '0' },
      },
      shadows: {
        floating: { value: 'var(--shadow-floating)' },
        panel: { value: 'var(--shadow-panel)' },
      },
    },
  },
});

export const system = createSystem(defaultConfig, config);
