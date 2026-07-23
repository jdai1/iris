const assert = require('node:assert/strict');
require('./anchoring.js');

const text = 'First repeated phrase. Middle. Second repeated phrase. End.';
assert.deepEqual(IrisAnchoring.locateOffsets(text, {
  quote: 'repeated phrase', start_offset: 6, end_offset: 21, prefix: 'First ', suffix: '.',
}), { start: 6, end: 21, strategy: 'position' });

assert.deepEqual(IrisAnchoring.locateOffsets(text, {
  quote: 'repeated phrase', start_offset: 0, end_offset: 15, prefix: 'Second ', suffix: '.',
}), { start: 38, end: 53, strategy: 'quote' });

assert.equal(IrisAnchoring.locateOffsets(text, { quote: 'missing', prefix: '', suffix: '' }), null);
console.log('anchoring strategies verified');
