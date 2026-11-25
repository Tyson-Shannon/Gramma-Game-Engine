'use strict';

const assert = require('assert');
const path = require('path');
const {
    DIAGNOSTIC_RE, matchesDocument, parseDiagnostics,
} = require('./diagnostics');

const output = [
    'grain OK: src/game.grain',
    'src/game.grain:12:5: error: unknown identifier \'nope\'',
    'src/other.grain:3:1: error: array literal has 1 element(s), expected 2',
].join('\n');

const parsed = parseDiagnostics(output);
assert.strictEqual(parsed.length, 2);
assert.deepStrictEqual(parsed[0], {
    filename: 'src/game.grain',
    line: 12,
    column: 5,
    message: 'unknown identifier \'nope\'',
});
assert.strictEqual(parsed[1].line, 3);
assert.ok(DIAGNOSTIC_RE.test('a.grain:1:2: error: bad'));

const root = path.resolve(__dirname, '..', '..', 'examples', 'grain-demo');
assert.ok(matchesDocument(parsed[0], path.join(root, 'src', 'game.grain'), root));
assert.ok(!matchesDocument(parsed[0], path.join(root, 'src', 'other.grain'), root));

console.log('VS Code Grain diagnostics OK');
