'use strict';

const assert = require('assert');
const path = require('path');
const {
    DIAGNOSTIC_RE, matchesDocument, parseDiagnostics,
} = require('./diagnostics');
const {
    MessageReader, encodeMessage,
} = require('./lsp-client');

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

// LSP framing must survive chunked stdio writes.
const messages = [
    { jsonrpc: '2.0', id: 1, method: 'initialize', params: {} },
    { jsonrpc: '2.0', method: 'textDocument/didOpen', params: { uri: 'file:///x' } },
];
const wire = Buffer.concat(messages.map(encodeMessage));
const received = [];
const reader = new MessageReader((message) => received.push(message));
for (const byte of wire) {
    reader.push(Buffer.from([byte]));
}
assert.deepStrictEqual(received, messages);

console.log('VS Code Grain adapter and LSP framing OK');
