'use strict';

const { execFile } = require('child_process');
const fs = require('fs');
const path = require('path');
const vscode = require('vscode');
const { matchesDocument, parseDiagnostics } = require('./diagnostics');
const { LanguageClient } = require('./lsp-client');

let diagnostics;
let client = null;
let lspReady = false;
const timers = new Map();

function findProjectRoot(filePath) {
    let directory = path.dirname(path.resolve(filePath));
    const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
    let fallback = workspaceRoot || directory;
    while (true) {
        if (fs.existsSync(path.join(directory, 'project.toml'))) {
            return directory;
        }
        const parent = path.dirname(directory);
        if (parent === directory) {
            return fallback;
        }
        directory = parent;
    }
}

function findCli(projectRoot, workspaceRoot, configured) {
    const candidates = [];
    if (path.isAbsolute(configured)) {
        candidates.push(configured);
    } else {
        candidates.push(path.resolve(workspaceRoot, configured));
        candidates.push(path.resolve(projectRoot, configured));
    }
    let directory = projectRoot;
    while (true) {
        candidates.push(path.join(directory, 'tools', 'gr', 'gr'));
        const parent = path.dirname(directory);
        if (parent === directory) {
            break;
        }
        directory = parent;
    }
    return candidates.find((candidate) => {
        try {
            fs.accessSync(candidate, fs.constants.X_OK);
            return true;
        } catch (_error) {
            return false;
        }
    });
}

function firstGrainDocument() {
    return vscode.workspace.textDocuments.find(
        (document) => document.languageId === 'grain');
}

// --- Fallback: the original thin `gr grain --check` adapter ----------------

function schedule(document) {
    if (lspReady || document.languageId !== 'grain'
            || document.uri.scheme !== 'file') {
        return;
    }
    const key = document.uri.toString();
    const existing = timers.get(key);
    if (existing) {
        clearTimeout(existing);
    }
    timers.set(key, setTimeout(() => {
        timers.delete(key);
        if (!lspReady) {
            check(document);
        }
    }, 300));
}

function check(document) {
    const root = findProjectRoot(document.uri.fsPath);
    const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath
        || root;
    const configured = vscode.workspace
        .getConfiguration('grain', document.uri)
        .get('cliPath', 'tools/gr/gr');
    const cli = findCli(root, workspaceRoot, configured);
    if (!cli) {
        reportCliError(document, `gr CLI not found (grain.cliPath = ${configured})`);
        return;
    }
    execFile(cli, ['grain', '--check', '--project', root],
             { cwd: root, timeout: 15000 },
             (error, stdout, stderr) => {
                 if (lspReady) {
                     return;
                 }
                 const parsed = parseDiagnostics(`${stdout}\n${stderr}`);
                 const documents = vscode.workspace.textDocuments
                     .filter((candidate) => candidate.languageId === 'grain');
                 for (const candidate of documents) {
                     const matches = parsed.filter((entry) =>
                         matchesDocument(entry, candidate.uri.fsPath, root));
                     diagnostics.set(candidate.uri, matches.map(toDiagnostic));
                 }
                 if (error && parsed.length === 0) {
                     reportCliError(document, String(stderr || error.message).trim());
                 }
             });
}

function toDiagnostic(entry) {
    const start = new vscode.Position(
        Math.max(0, entry.line - 1), Math.max(0, entry.column - 1));
    const range = new vscode.Range(start, start.translate(0, 1));
    const diagnostic = new vscode.Diagnostic(
        range, entry.message, vscode.DiagnosticSeverity.Error);
    diagnostic.source = 'grain';
    return diagnostic;
}

function reportCliError(document, message) {
    const range = new vscode.Range(0, 0, 0, 0);
    const diagnostic = new vscode.Diagnostic(
        range, message, vscode.DiagnosticSeverity.Error);
    diagnostic.source = 'grain';
    diagnostics.set(document.uri, [diagnostic]);
}

// --- Language server client ------------------------------------------------

function documentParams(document) {
    return { textDocument: { uri: document.uri.toString() } };
}

function asPosition(position) {
    return new vscode.Position(position.line, position.character);
}

function asRange(range) {
    return new vscode.Range(asPosition(range.start), asPosition(range.end));
}

const COMPLETION_KINDS = {
    3: vscode.CompletionItemKind.Function,
    5: vscode.CompletionItemKind.Field,
    6: vscode.CompletionItemKind.Variable,
    7: vscode.CompletionItemKind.Class,
    13: vscode.CompletionItemKind.Variable,
    14: vscode.CompletionItemKind.Keyword,
    20: vscode.CompletionItemKind.Constant,
    21: vscode.CompletionItemKind.Module,
    22: vscode.CompletionItemKind.Struct,
};

const SYMBOL_KINDS = {
    5: vscode.SymbolKind.Class,
    6: vscode.SymbolKind.Function,
    8: vscode.SymbolKind.Field,
    13: vscode.SymbolKind.Variable,
};

function registerLanguageFeatures(context) {
    const selector = { language: 'grain', scheme: 'file' };
    context.subscriptions.push(vscode.languages.registerCompletionItemProvider(
        selector, {
            async provideCompletionItems(document, position) {
                if (!lspReady) {
                    return [];
                }
                const items = await client.request('textDocument/completion', {
                    ...documentParams(document),
                    position: { line: position.line, character: position.character },
                });
                return (items || []).map((item) => {
                    const completion = new vscode.CompletionItem(item.label);
                    completion.kind = COMPLETION_KINDS[item.kind]
                        || vscode.CompletionItemKind.Text;
                    completion.detail = item.detail || '';
                    return completion;
                });
            },
        }, '.', '('));

    context.subscriptions.push(vscode.languages.registerDefinitionProvider(
        selector, {
            async provideDefinition(document, position) {
                if (!lspReady) {
                    return [];
                }
                const locations = await client.request('textDocument/definition', {
                    ...documentParams(document),
                    position: { line: position.line, character: position.character },
                });
                return (locations || []).map((location) =>
                    new vscode.Location(vscode.Uri.parse(location.uri),
                                        asRange(location.range)));
            },
        }));

    context.subscriptions.push(vscode.languages.registerRenameProvider(
        selector, {
            async provideRenameEdits(document, position, newName) {
                const edit = await client.request('textDocument/rename', {
                    ...documentParams(document),
                    position: { line: position.line, character: position.character },
                    newName,
                });
                if (!edit || !edit.changes) {
                    return null;
                }
                const workspaceEdit = new vscode.WorkspaceEdit();
                for (const [uri, changes] of Object.entries(edit.changes)) {
                    for (const change of changes) {
                        workspaceEdit.replace(vscode.Uri.parse(uri),
                                              asRange(change.range),
                                              change.newText);
                    }
                }
                return workspaceEdit;
            },
        }));

    context.subscriptions.push(vscode.languages.registerHoverProvider(
        selector, {
            async provideHover(document, position) {
                if (!lspReady) {
                    return null;
                }
                const hover = await client.request('textDocument/hover', {
                    ...documentParams(document),
                    position: { line: position.line, character: position.character },
                });
                if (!hover) {
                    return null;
                }
                return new vscode.Hover(hover.contents.value);
            },
        }));

    context.subscriptions.push(vscode.languages.registerDocumentSymbolProvider(
        selector, {
            async provideDocumentSymbols(document) {
                if (!lspReady) {
                    return [];
                }
                const symbols = await client.request('textDocument/documentSymbol',
                                                     documentParams(document));
                return (symbols || []).map((symbol) =>
                    new vscode.DocumentSymbol(
                        symbol.name, symbol.detail || '',
                        SYMBOL_KINDS[symbol.kind] || vscode.SymbolKind.Variable,
                        asRange(symbol.range), asRange(symbol.selectionRange)));
            },
        }));
}

function startLanguageServer(context, root, workspaceRoot) {
    const configured = vscode.workspace.getConfiguration('grain')
        .get('cliPath', 'tools/gr/gr');
    const cli = findCli(root, workspaceRoot, configured);
    if (!cli) {
        return false;
    }
    let server;
    try {
        server = new LanguageClient(cli, ['lsp'], { cwd: root });
        server.onNotification('textDocument/publishDiagnostics', (params) => {
            const uri = vscode.Uri.parse(params.uri);
            diagnostics.set(uri, (params.diagnostics || []).map((entry) => {
                const diagnostic = new vscode.Diagnostic(
                    asRange(entry.range), entry.message,
                    vscode.DiagnosticSeverity.Error);
                diagnostic.source = 'grain';
                return diagnostic;
            }));
        });
        server.start().then(() => {
            server.notify('initialized', {});
            lspReady = true;
            for (const document of vscode.workspace.textDocuments) {
                if (document.languageId === 'grain' && document.uri.scheme === 'file') {
                    server.notify('textDocument/didOpen', {
                        textDocument: {
                            uri: document.uri.toString(),
                            languageId: 'grain',
                            version: 1,
                            text: document.getText(),
                        },
                    });
                }
            }
        }, (error) => {
            lspReady = false;
            console.warn(`Grain language server unavailable: ${error.message}`);
        });
    } catch (_error) {
        return false;
    }
    client = server;
    context.subscriptions.push({ dispose: () => server.stop() });
    registerLanguageFeatures(context);
    return true;
}

function activate(context) {
    diagnostics = vscode.languages.createDiagnosticCollection('grain');
    context.subscriptions.push(diagnostics);
    const document = firstGrainDocument();
    const root = document ? findProjectRoot(document.uri.fsPath)
        : (vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || process.cwd());
    const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath
        || root;
    const started = startLanguageServer(context, root, workspaceRoot);

    context.subscriptions.push(vscode.workspace.onDidOpenTextDocument((opened) => {
        if (lspReady && opened.languageId === 'grain' && opened.uri.scheme === 'file') {
            client.notify('textDocument/didOpen', {
                textDocument: {
                    uri: opened.uri.toString(), languageId: 'grain',
                    version: 1, text: opened.getText(),
                },
            });
        } else {
            schedule(opened);
        }
    }));
    context.subscriptions.push(vscode.workspace.onDidChangeTextDocument((event) => {
        if (lspReady && event.document.languageId === 'grain'
                && event.document.uri.scheme === 'file') {
            client.notify('textDocument/didChange', {
                textDocument: { uri: event.document.uri.toString(), version: 2 },
                contentChanges: [{ text: event.document.getText() }],
            });
        } else {
            schedule(event.document);
        }
    }));
    context.subscriptions.push(vscode.workspace.onDidSaveTextDocument(schedule));
    context.subscriptions.push(vscode.workspace.onDidCloseTextDocument((closed) => {
        const key = closed.uri.toString();
        const timer = timers.get(key);
        if (timer) {
            clearTimeout(timer);
            timers.delete(key);
        }
        if (lspReady && closed.languageId === 'grain') {
            client.notify('textDocument/didClose', documentParams(closed));
        }
        diagnostics.delete(closed.uri);
    }));
    vscode.workspace.textDocuments.forEach(schedule);
    if (!started) {
        vscode.workspace.textDocuments.forEach((opened) => {
            if (opened.languageId === 'grain') {
                check(opened);
            }
        });
    }
}

function deactivate() {
    for (const timer of timers.values()) {
        clearTimeout(timer);
    }
    timers.clear();
    if (client) {
        client.stop();
        client = null;
    }
    lspReady = false;
}

module.exports = { activate, deactivate };
