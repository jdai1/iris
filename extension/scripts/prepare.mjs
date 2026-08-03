import { cp, mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const extensionDir = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const repoDir = resolve(extensionDir, '..');
const distDir = resolve(extensionDir, 'dist');
const uiBuildDir = resolve(extensionDir, 'build/ui');
const profile = process.argv[2] ?? 'local';
const environments = JSON.parse(await readFile(resolve(repoDir, 'config/environments.json'), 'utf8'));
const environment = environments[profile];

if (!environment) {
  throw new Error(`Unknown extension environment: ${profile}`);
}

await rm(distDir, { recursive: true, force: true });
await mkdir(distDir, { recursive: true });
await cp(uiBuildDir, distDir, { recursive: true });
for (const file of ['background.js', 'content.js', 'content.css', 'anchoring.js']) {
  await cp(resolve(extensionDir, file), resolve(distDir, file));
}
await cp(resolve(extensionDir, 'icons'), resolve(distDir, 'icons'), { recursive: true });

const configSource = `export const IRIS_CONFIG = Object.freeze(${JSON.stringify({
  profile,
  appBase: environment.appBase,
  apiBase: environment.apiBase,
}, null, 2)});\n`;
await writeFile(resolve(distDir, 'config.js'), configSource);

const apiOrigin = new URL(environment.apiBase).origin;
const appOrigin = new URL(environment.appBase).origin;
const manifest = {
  manifest_version: 3,
  name: 'Save to Iris',
  version: '1.0.0',
  description: 'Save pages, notes, and highlights to your Iris bookshelf.',
  permissions: ['activeTab', 'storage'],
  host_permissions: [`${apiOrigin}/*`, 'https://securetoken.googleapis.com/*'],
  externally_connectable: { matches: [`${appOrigin}/*`] },
  action: {
    default_title: 'Save to Iris',
    default_popup: 'popup.html',
    default_icon: {
      16: 'icons/iris-16.png',
      32: 'icons/iris-32.png',
      48: 'icons/iris-48.png',
    },
  },
  icons: {
    16: 'icons/iris-16.png',
    32: 'icons/iris-32.png',
    48: 'icons/iris-48.png',
    128: 'icons/iris-128.png',
  },
  background: { service_worker: 'background.js', type: 'module' },
  content_scripts: [{
    matches: ['http://*/*', 'https://*/*'],
    js: ['anchoring.js', 'content.js'],
    css: ['content.css'],
    run_at: 'document_idle',
  }],
  web_accessible_resources: [{
    resources: ['icons/iris-mark.svg'],
    matches: ['http://*/*', 'https://*/*'],
  }],
  options_page: 'settings.html',
};
await writeFile(resolve(distDir, 'manifest.json'), `${JSON.stringify(manifest, null, 2)}\n`);
