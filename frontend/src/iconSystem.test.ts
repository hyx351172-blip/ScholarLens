import assert from 'node:assert/strict';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, resolve } from 'node:path';
import test from 'node:test';

function collectTsxFiles(directory: string): string[] {
  return readdirSync(directory).flatMap((entry) => {
    const path = join(directory, entry);
    return statSync(path).isDirectory()
      ? collectTsxFiles(path)
      : path.endsWith('.tsx')
        ? [path]
        : [];
  });
}

test('product UI uses vector icons instead of pictographic emoji', () => {
  const emoji = /\p{Extended_Pictographic}/u;
  const offenders = collectTsxFiles(resolve(process.cwd(), 'components')).filter((path) =>
    emoji.test(readFileSync(path, 'utf8')),
  );

  assert.deepEqual(offenders, []);
});

test('Lucide icons share the academic outline stroke token', () => {
  const stylesheet = readFileSync(resolve(process.cwd(), 'styles', 'globals.css'), 'utf8');

  assert.match(stylesheet, /\.lucide\s*\{[^}]*stroke-width:\s*1\.75;/s);
});
