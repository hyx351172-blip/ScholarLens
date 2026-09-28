import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import remarkEvidenceCitations from '../src/remarkEvidenceCitations.ts';

function render(content: string) {
  return renderToStaticMarkup(createElement(ReactMarkdown, {
    remarkPlugins: [remarkMath, remarkEvidenceCitations],
    rehypePlugins: [[rehypeKatex, { trust: false, maxExpand: 1000 }]],
    children: content,
  }));
}

test('AC-4905 real markdown pipeline renders math and moves its citation outside', () => {
  const html = render('公式：\n\n$$\n\\text{softmax}\\left(\\frac{QK^T}{\\sqrt{d_k}}\\right)V \\quad [S2]\n$$\n\n解释 $d_k$ [S1]。');
  assert.match(html, /class="katex-display"/);
  assert.doesNotMatch(html, /katex-error/);
  assert.match(html, /href="#evidence-S2"/);
  assert.match(html, /href="#evidence-S1"/);
  assert.doesNotMatch(html, /\[S2\]/);
  assert.ok(html.indexOf('class="katex') < html.indexOf('href="#evidence-S2"'));
});

test('AC-4905 same-line math citations also survive without corrupting TeX', () => {
  const html = render('公式 $$ QK^T/\\sqrt{d_k} [S2] $$ 和 $d_k$。');
  assert.match(html, /class="katex"/);
  assert.match(html, /href="#evidence-S2"/);
  assert.doesNotMatch(html, /katex-error/);
});

test('AC-4905 code and pre-existing links are not rewritten', () => {
  const html = render('`[S1]`\n\n```text\n[S2]\n```\n\n[S3](#evidence-S3) 和 [S4][S5]');
  assert.match(html, /<code>\[S1\]<\/code>/);
  assert.match(html, /\[S2\]/);
  assert.equal((html.match(/href="#evidence-S3"/g) ?? []).length, 1);
  assert.match(html, /href="#evidence-S4"/);
  assert.match(html, /href="#evidence-S5"/);
});

test('AC-4905 untrusted math cannot create remote links or raw HTML', () => {
  const html = render('$\\href{https://evil.invalid}{x}$\n\n<script>alert(1)</script>');
  assert.doesNotMatch(html, /href="https:\/\/evil.invalid"/);
  assert.doesNotMatch(html, /<script>/);
});

test('AC-4906 narrow-screen controls and knowledge-base isolation are wired', () => {
  const chat = readFileSync(new URL('../components/Chat.tsx', import.meta.url), 'utf8');
  assert.doesNotMatch(chat, /className="relative hidden sm:block"/);
  assert.match(chat, /aria-label="窄屏新建对话"/);
  assert.match(chat, /aria-label="历史对话"/);
  assert.match(chat, /handleKnowledgeBaseChange\(event.target.value\)/);
  assert.match(chat, /if \(isLoading\) return;/);
});
