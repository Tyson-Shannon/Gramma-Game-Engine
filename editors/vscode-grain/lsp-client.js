'use strict';

// Minimal LSP JSON-RPC client over stdio. The extension avoids adding an npm
// dependency: the server is the `gr lsp` subcommand shipped with this repo.

const { spawn } = require('child_process');

function encodeMessage(message) {
    const body = Buffer.from(JSON.stringify(message), 'utf8');
    const header = Buffer.from(`Content-Length: ${body.length}\r\n\r\n`, 'ascii');
    return Buffer.concat([header, body]);
}

class MessageReader {
    constructor(onMessage) {
        this.onMessage = onMessage;
        this.buffer = Buffer.alloc(0);
    }

    push(chunk) {
        this.buffer = this.buffer.length === 0
            ? Buffer.from(chunk)
            : Buffer.concat([this.buffer, Buffer.from(chunk)]);
        while (true) {
            const split = this.buffer.indexOf('\r\n\r\n');
            if (split < 0) {
                return;
            }
            const header = this.buffer.slice(0, split).toString('ascii');
            const match = /content-length:\s*(\d+)/i.exec(header);
            if (!match) {
                this.buffer = this.buffer.slice(split + 4);
                continue;
            }
            const length = Number(match[1]);
            const start = split + 4;
            if (this.buffer.length < start + length) {
                return;
            }
            const body = this.buffer.slice(start, start + length);
            this.buffer = this.buffer.slice(start + length);
            this.onMessage(JSON.parse(body.toString('utf8')));
        }
    }
}

class LanguageClient {
    constructor(command, args, options = {}) {
        this.command = command;
        this.args = args;
        this.options = options;
        this.nextId = 1;
        this.pending = new Map();
        this.notifications = new Map();
        this.child = null;
    }

    start() {
        this.child = spawn(this.command, this.args, {
            cwd: this.options.cwd,
            stdio: ['pipe', 'pipe', 'pipe'],
        });
        const reader = new MessageReader((message) => this._handle(message));
        this.child.stdout.on('data', (chunk) => reader.push(chunk));
        this.child.on('exit', (code) => {
            for (const pending of this.pending.values()) {
                pending.reject(new Error(`gr lsp exited with ${code}`));
            }
            this.pending.clear();
        });
        return this.request('initialize', {
            processId: process.pid,
            rootUri: null,
            capabilities: {},
        });
    }

    request(method, params = {}) {
        const id = this.nextId++;
        return new Promise((resolve, reject) => {
            this.pending.set(id, { resolve, reject });
            this._write({ jsonrpc: '2.0', id, method, params });
        });
    }

    notify(method, params = {}) {
        this._write({ jsonrpc: '2.0', method, params });
    }

    onNotification(method, handler) {
        this.notifications.set(method, handler);
    }

    stop() {
        if (this.child && !this.child.killed) {
            this.child.kill();
        }
    }

    _write(message) {
        if (!this.child || !this.child.stdin) {
            throw new Error('gr lsp is not running');
        }
        this.child.stdin.write(encodeMessage(message));
    }

    _handle(message) {
        if (message.id !== undefined && message.method === undefined) {
            const pending = this.pending.get(message.id);
            if (!pending) {
                return;
            }
            this.pending.delete(message.id);
            if (message.error) {
                pending.reject(new Error(message.error.message));
            } else {
                pending.resolve(message.result);
            }
            return;
        }
        const handler = this.notifications.get(message.method);
        if (handler) {
            handler(message.params);
        }
    }
}

module.exports = { LanguageClient, MessageReader, encodeMessage };
