import { mkdir, rm } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const extensionDir = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const releaseDir = resolve(extensionDir, 'release');
const archive = resolve(releaseDir, 'save-to-iris-1.0.0.zip');

await mkdir(releaseDir, { recursive: true });
await rm(archive, { force: true });
const result = spawnSync('/usr/bin/zip', ['-qr', archive, '.'], {
  cwd: resolve(extensionDir, 'dist'),
  stdio: 'inherit',
});
if (result.status !== 0) process.exit(result.status ?? 1);
console.log(archive);
