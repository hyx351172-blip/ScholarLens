import assert from 'node:assert/strict';
import test from 'node:test';

import { buttonStyles } from '../components/ui/button.ts';

test('command buttons share a pill shape and visible keyboard focus', () => {
  const className = buttonStyles();

  assert.match(className, /rounded-full/);
  assert.match(className, /focus-visible:ring-2/);
  assert.match(className, /disabled:pointer-events-none/);
});

test('button variants communicate hierarchy without changing geometry', () => {
  const primary = buttonStyles({ variant: 'primary' });
  const secondary = buttonStyles({ variant: 'secondary' });
  const dangerIcon = buttonStyles({ variant: 'danger', iconOnly: true, size: 'sm' });

  assert.match(primary, /bg-violet-600/);
  assert.match(secondary, /bg-white/);
  assert.match(dangerIcon, /text-rose-600/);
  assert.match(dangerIcon, /h-8/);
  assert.match(dangerIcon, /w-8/);
});
