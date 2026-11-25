'use strict';

const { execFile } = require('child_process');
const fs = require('fs');
const path = require('path');
const vscode = require('vscode');
const { matchesDocument, parseDiagnostics } = require('./diagnostics');

let diagnostics;
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

function schedule(document) {
    if (document.languageId !== 'grain' || document.uri.scheme !== 'file') {
        return;
    }
    const key = document.uri.toString();
    const existing = timers.get(key);
    if (existing) {
        clearTimeout(existing);
    }
    timers.set(key, setTimeout(() => {
        timers.delete(key);
        check(document);
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

function activate(context) {
    diagnostics = vscode.languages.createDiagnosticCollection('grain');
    context.subscriptions.push(diagnostics);
    context.subscriptions.push(vscode.workspace.onDidOpenTextDocument(schedule));
    context.subscriptions.push(vscode.workspace.onDidChangeTextDocument((event) =>
        schedule(event.document)));
    context.subscriptions.push(vscode.workspace.onDidSaveTextDocument(schedule));
    context.subscriptions.push(vscode.workspace.onDidCloseTextDocument((document) => {
        const key = document.uri.toString();
        const timer = timers.get(key);
        if (timer) {
            clearTimeout(timer);
            timers.delete(key);
        }
        diagnostics.delete(document.uri);
    }));
    vscode.workspace.textDocuments.forEach(schedule);
}

function deactivate() {
    for (const timer of timers.values()) {
        clearTimeout(timer);
    }
    timers.clear();
}

module.exports = { activate, deactivate };
