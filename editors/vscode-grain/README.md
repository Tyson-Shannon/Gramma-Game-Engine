# Grain for VS Code

Syntax highlighting and live diagnostics for Grain (`.grain`) sources. The
extension does not ship a language server: it runs the project's `gr grain
--check` command and maps `file:line:col: error: ...` lines to VS Code problems.

## Install

From the repository root:

```sh
cd editors/vscode-grain
npm install -g @vscode/vsce   # once
vsce package
code --install-extension grain-gramma-0.1.0.vsix
```

Or copy/symlink `editors/vscode-grain` into your VS Code extensions directory
for development and press F5 in the extension folder.

## Use

Open any `.grain` file inside a Gramma project (a directory with
`project.toml`). Diagnostics are refreshed on open, change and save. The
extension walks up from the open file to find the project root, then walks up
again to find `tools/gr/gr` unless `grain.cliPath` is set explicitly:

```json
{
  "grain.cliPath": "/absolute/path/to/gr"
}
```

Relative paths are resolved against the workspace folder and the project root.
Only `gr grain --check` is used; nothing is transpiled or built by the
extension. Run the adapter test with `node test.js` (or `npm test`).
