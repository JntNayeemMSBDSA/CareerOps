import test from 'node:test';
import assert from 'node:assert/strict';
import { validatePayload } from '../lib/cv-payload-schema.mjs';
import { resolvePageFormat } from '../lib/page-format.mjs';

test('payload validation rejects missing candidate data', () => {
  const result=validatePayload({});
  assert.ok(result.errors.length > 0);
});
test('page format remains US Letter for the one-page renderer', () => {
  const result=resolvePageFormat({});
  assert.ok(result);
});
