import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import test from 'node:test';

const uploadDialog = readFileSync(
  resolve(process.cwd(), 'components', 'UploadDialog.tsx'),
  'utf8',
);
const chat = readFileSync(resolve(process.cwd(), 'components', 'Chat.tsx'), 'utf8');

test('scientific PDF uploads default to Docling structure-aware parsing', () => {
  assert.match(uploadDialog, /extractionMode:\s*'docling'/);
  assert.match(uploadDialog, /formData\.append\('enable_vlm_repair'/);
  assert.match(uploadDialog, /appConfig\.extractionApiUrl/);
  assert.match(uploadDialog, /appConfig\.milvusApiUrl/);
});

test('chat uses the validated dense retrieval threshold', () => {
  assert.match(chat, /score_threshold:\s*0\.1/);
  assert.doesNotMatch(chat, /score_threshold:\s*0\.3/);
});

