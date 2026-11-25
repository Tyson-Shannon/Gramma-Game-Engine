'use strict';

const path = require('path');

// gr grain --check writes "file:line:col: error: message" to stderr.
const DIAGNOSTIC_RE = /^(.*):(\d+):(\d+): error: (.*)$/;

function parseDiagnostics(text) {
    const result = [];
    for (const line of String(text).split(/\r?\n/)) {
        const match = DIAGNOSTIC_RE.exec(line.trim());
        if (!match) {
            continue;
        }
        result.push({
            filename: match[1],
            line: Number(match[2]),
            column: Number(match[3]),
            message: match[4],
        });
    }
    return result;
}

function matchesDocument(diagnostic, filePath, root) {
    const absoluteFile = path.resolve(filePath);
    if (path.isAbsolute(diagnostic.filename)) {
        return path.resolve(diagnostic.filename) === absoluteFile;
    }
    const reported = path.resolve(root, diagnostic.filename);
    if (reported === absoluteFile) {
        return true;
    }
    const relative = path.relative(root, absoluteFile).replace(/\\/g, '/');
    return diagnostic.filename === relative
        || diagnostic.filename.endsWith('/' + relative)
        || path.basename(diagnostic.filename) === path.basename(absoluteFile);
}

module.exports = { DIAGNOSTIC_RE, matchesDocument, parseDiagnostics };
