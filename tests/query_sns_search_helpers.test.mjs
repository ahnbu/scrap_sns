import test from 'node:test';
import assert from 'node:assert/strict';
import { matchesSearchText, normalizeSearchText } from '../utils/query-sns.mjs';

test('normalizeSearchText treats hyphen and underscore as spaces', () => {
  assert.equal(normalizeSearchText('slides-grab'), 'slides grab');
  assert.equal(normalizeSearchText('slides_grab'), 'slides grab');
});

test('matchesSearchText finds hyphenated names with space-separated query terms', () => {
  const text = 'slides-grab is an HTML slide editor';

  assert.equal(matchesSearchText(text, 'slides-grab'), true);
  assert.equal(matchesSearchText(text, 'slides grab'), true);
  assert.equal(matchesSearchText(text, 'slide grab'), true);
  assert.equal(matchesSearchText(text, 'slide-grab'), true);
});

test('matchesSearchText does not correct grap to grab', () => {
  assert.equal(matchesSearchText('slides-grab is an HTML slide editor', 'slide grap'), false);
});
