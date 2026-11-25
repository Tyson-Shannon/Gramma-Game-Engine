"""Host-side JSON service for GUI and other external clients.

The protocol is JSON-RPC 2.0 over newline-delimited JSON on stdio. It is a thin
adapter over the existing pipeline and build drivers: no GUI framework, project
cache format or editor-specific concept lives in this module. Human-readable
output from the CLI is redirected to stderr so stdout stays a clean protocol
stream.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
from contextlib import contextmanager
from pathlib import Path

from gramma_pipeline import (
    MANIFEST_SCHEMA_VERSION, PROJECT_SCHEMA_VERSION, SERVICE_CONTRACT_VERSION,
    build_api_reference, check_budget_detailed, generate_api_reference,
    load_project)
from gramma_pipeline.grain import GrainError, check_grain, transpile
from gramma_pipeline.targets import TARGET_STATUS

from .template import TEMPLATES, create_project

METHODS = (
    "service.version",
    "service.capabilities",
    "project.create",
    "project.open",
    "project.validate",
    "project.save",
    "assets.list",
    "assets.generate",
    "grain.check",
    "grain.transpile",
    "check",
    "build",
    "run",
    "targets",
    "doctor",
    "docs.generate",
    "docs.check",
)


class ServiceError(Exception):
    """A structured, client-facing protocol error."""

    def __init__(self, code: str, message: str, data=None,
                 rpc_code: int = -32000):
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data
        self.rpc_code = rpc_code

    def as_dict(self) -> dict:
        error = {"code": self.rpc_code, "message": self.message}
        if self.data is not None:
            error["data"] = self.data
        return error


def _cli():
    """Import the CLI lazily so `gr serve` cannot create an import cycle."""
    from . import main as cli
    return cli


@contextmanager
def _stdout_to_stderr():
    """Keep CLI/build chatter off the JSON response stream."""
    saved = sys.stdout
    sys.stdout = sys.stderr
    try:
        yield
    finally:
        sys.stdout = saved


def _require_params(params) -> dict:
    if params is None:
        return {}
    if not isinstance(params, dict):
        raise ServiceError("invalid_params", "params must be an object",
                           rpc_code=-32602)
    return params


def _root(params: dict) -> Path:
    cli = _cli()
    try:
        return cli._find_project(params.get("project"))
    except FileNotFoundError as error:
        raise ServiceError("project_not_found", str(error)) from error


def _load(params: dict):
    root = _root(params)
    try:
        return root, load_project(root)
    except (FileNotFoundError, ValueError) as error:
        raise ServiceError("project_invalid", str(error)) from error


def _target(params: dict, root: Path) -> str:
    return params.get("target") or _cli()._default_target(root)


def _mapper(params: dict) -> dict | None:
    value = params.get("mapper_override")
    if value is None:
        value = params.get("mapper")
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ServiceError("invalid_params",
                           "mapper_override must be an object",
                           rpc_code=-32602)
    return dict(value)


def _relative(root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def _asset_summary(project) -> dict:
    return {
        "image": [{"name": item.name, "file": str(item.file),
                   "kind": item.kind, "bpp": item.bpp}
                  for item in project.images],
        "audio": [{"name": item.name, "file": str(item.file),
                   "sample_rate": item.sample_rate}
                  for item in project.audio],
        "music": [{"name": item.name, "file": str(item.file)}
                  for item in project.music],
        "map": [{"name": item.name, "file": str(item.file),
                 "layer": item.layer, "bpp": item.bpp}
                for item in project.maps],
    }


def _project_open(root: Path) -> dict:
    project = load_project(root)
    return {
        "root": str(root.resolve()),
        "schema_version": project.schema_version,
        "project": {
            "name": project.name,
            "default_target": project.default_target,
            "max_sprites": project.max_sprites,
        },
        "assets": _asset_summary(project),
        "grain_sources": [_relative(root, source)
                          for source in project.grain_sources],
        "mapper": project.mapper,
        "budgets": project.budgets,
        "targets": project.targets,
    }


def _service_version() -> dict:
    return {
        "service": "gramma",
        "contract_version": SERVICE_CONTRACT_VERSION,
        "project_schema_version": PROJECT_SCHEMA_VERSION,
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "methods": list(METHODS),
    }


def _service_capabilities() -> dict:
    cli = _cli()
    return {
        **_service_version(),
        "transport": "jsonrpc-2.0/ndjson",
        "templates": sorted(TEMPLATES),
        "targets": sorted(TARGET_STATUS),
        "target_status": dict(TARGET_STATUS),
        "gui_framework_dependency": False,
    }


def _project_create(params: dict) -> dict:
    directory_value = params.get("directory")
    if not directory_value:
        raise ServiceError("invalid_params", "directory is required",
                           rpc_code=-32602)
    template = params.get("template", "c")
    if template not in TEMPLATES:
        raise ServiceError("invalid_params",
                           f"unknown template '{template}'",
                           {"templates": sorted(TEMPLATES)}, -32602)
    directory = Path(directory_value).resolve()
    name = params.get("name") or directory.name
    if directory.exists():
        raise ServiceError("project_exists", f"{directory} already exists")
    create_project(directory, name, template)
    return _project_open(directory)


def _project_validate(params: dict) -> dict:
    root, project = _load(params)
    missing = [str(path) for path in
               project.images + project.audio + project.music + project.maps
               + project.grain_sources
               if not path.is_file()]
    return {
        "ok": not missing,
        "root": str(root.resolve()),
        "schema_version": project.schema_version,
        "missing_files": missing,
    }


def _project_save(params: dict) -> dict:
    root = _root(params)
    content = params.get("content")
    if not isinstance(content, str):
        raise ServiceError("invalid_params", "content must be TOML text",
                           rpc_code=-32602)
    path = root / "project.toml"
    if not path.is_file():
        raise ServiceError("project_not_found", f"no project.toml in {root}")
    try:
        data = tomllib.loads(content)
    except tomllib.TOMLDecodeError as error:
        raise ServiceError("invalid_toml", str(error), rpc_code=-32602) from error
    try:
        version = int(data.get("project", {}).get("schema_version", 1))
    except (TypeError, ValueError) as error:
        raise ServiceError("invalid_params",
                           "project.schema_version must be an integer",
                           rpc_code=-32602) from error
    if version > PROJECT_SCHEMA_VERSION:
        raise ServiceError("unsupported_schema",
                           f"project schema {version} is newer than "
                           f"supported version {PROJECT_SCHEMA_VERSION}",
                           {"supported": PROJECT_SCHEMA_VERSION})
    previous = path.read_text(encoding="utf-8")
    path.write_text(content, encoding="utf-8")
    try:
        load_project(root)
    except (FileNotFoundError, ValueError, KeyError, TypeError) as error:
        path.write_text(previous, encoding="utf-8")
        raise ServiceError("project_invalid", str(error),
                           rpc_code=-32602) from error
    return _project_open(root)


def _assets_list(params: dict) -> dict:
    root, project = _load(params)
    target = _target(params, root)
    manifest_path = root / "generated" / target / "manifest.json"
    manifest = None
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            manifest = None
    return {
        "target": target,
        "declared": _asset_summary(project),
        "manifest": manifest,
        "manifest_path": str(manifest_path.resolve()),
        "manifest_present": manifest is not None,
    }


def _assets_generate(params: dict) -> dict:
    root, project = _load(params)
    target = _target(params, root)
    manifest = _cli().generate(root, target, project, _mapper(params))
    return {"target": target, "manifest": manifest}


def _grain_check(params: dict) -> dict:
    if isinstance(params.get("text"), str):
        source = str(params.get("source", "<grain>"))
        errors = check_grain(params["text"], source)
        diagnostics = [error.as_dict() for error in errors]
        return {"ok": not diagnostics, "source": source,
                "diagnostics": diagnostics}

    root, project = _load(params)
    source: str | None = params.get("source")
    if source is not None:
        path = Path(source)
        if not path.is_absolute():
            path = root / path
        candidates = [path]
    else:
        candidates = list(project.grain_sources)
    if not candidates:
        raise ServiceError("no_grain_sources",
                           "no Grain sources in this project")
    results = []
    for path in candidates:
        if not path.is_file():
            raise ServiceError("source_not_found", f"Grain source not found: {path}")
        name = _relative(root, path)
        try:
            errors = check_grain(path.read_text(encoding="utf-8"), name)
        except GrainError as error:
            errors = [error]
        diagnostics = [error.as_dict() for error in errors]
        results.append({"source": name, "ok": not diagnostics,
                        "diagnostics": diagnostics})
    return {"ok": all(item["ok"] for item in results), "results": results}


def _grain_transpile(params: dict) -> dict:
    cli = _cli()
    if isinstance(params.get("text"), str):
        source = str(params.get("source", "<grain>"))
        text = params["text"]
        root = Path(params.get("project", "")).resolve() if params.get("project") else Path.cwd()
    else:
        root, project = _load(params)
        source_value = params.get("source")
        if source_value is None:
            if not project.grain_sources:
                raise ServiceError("no_grain_sources",
                                   "no Grain sources in this project")
            path = project.grain_sources[0]
        else:
            path = Path(source_value)
            if not path.is_absolute():
                path = root / path
        if not path.is_file():
            raise ServiceError("source_not_found", f"Grain source not found: {path}")
        source = _relative(root, path)
        text = path.read_text(encoding="utf-8")

    errors = check_grain(text, source)
    if errors:
        return {"ok": False, "source": source,
                "diagnostics": [error.as_dict() for error in errors]}
    try:
        c_text, checker = transpile(text, source)
    except GrainError as error:
        return {"ok": False, "source": source,
                "diagnostics": [error.as_dict()]}

    if params.get("out"):
        output = Path(params["out"]).resolve()
    else:
        target = _target(params, root)
        output = root / "generated" / target
    output.mkdir(parents=True, exist_ok=True)
    filename = "grain_" + re.sub(r"[^A-Za-z0-9_]", "_", Path(source).stem) + ".c"
    destination = output / filename
    destination.write_text(c_text, encoding="utf-8")
    return {
        "ok": True,
        "source": source,
        "file": str(destination.resolve()),
        "entities": [entity.name for entity in checker.program.entities],
        "scenes": [scene.name for scene in checker.program.scenes],
        "diagnostics": [],
    }


def _check(params: dict) -> dict:
    cli = _cli()
    root, project = _load(params)
    target = _target(params, root)
    manifest = cli.generate(root, target, project, _mapper(params))
    violations = check_budget_detailed(project, target, manifest)
    return {
        "ok": not violations,
        "target": target,
        "violations": violations,
        "diagnostics": violations,
        "manifest": manifest,
    }


def _build_or_run(params: dict, run: bool) -> dict:
    cli = _cli()
    root = _root(params)
    target = _target(params, root)
    status, artifact = cli._build(
        root, target, bool(params.get("release", False)),
        _mapper(params), bool(params.get("gg", False)))
    result = {
        "ok": status == 0,
        "status": status,
        "target": target,
        "artifact": str(artifact.resolve()) if artifact is not None else None,
    }
    if run and status == 0:
        if target != "pc":
            result["launched"] = False
            return result
        env = os.environ.copy()
        if params.get("scale") is not None:
            env["GRAMMA_SCALE"] = str(params["scale"])
        if params.get("frames") is not None:
            env["GRAMMA_TEST_FRAMES"] = str(params["frames"])
        exit_code = subprocess.call([str(artifact)], env=env)
        result.update({"launched": True, "exit_code": exit_code,
                       "ok": exit_code == 0})
    return result


def _doctor() -> dict:
    cli = _cli()
    tools = {name: shutil.which(name)
             for name in ("python3", "meson", "ninja", "gcc", "pkg-config")}
    try:
        import PIL
        pillow = PIL.__version__
    except ImportError:
        pillow = None
    return {
        "repo": str(cli.REPO),
        "python": sys.version.split()[0],
        "tools": tools,
        "pillow": pillow,
        "sdl2": cli.sdl_status(cli.REPO),
        "gbdk": cli.gbdk_status(),
        "cc65": cli.cc65_status(),
        "sms_gg": cli.sms_status(),
        "grain": "parser/typechecker/transpiler available",
    }


def _docs_generate() -> dict:
    path = generate_api_reference(_cli().REPO)
    return {"ok": True, "path": str(path)}


def _docs_check() -> dict:
    cli = _cli()
    path = cli.REPO / "docs" / "generated" / "api-reference.md"
    if not path.is_file():
        return {"ok": False, "path": str(path), "reason": "missing"}
    current = path.read_text(encoding="utf-8")
    expected = build_api_reference(cli.REPO)
    return {"ok": current == expected, "path": str(path),
            "reason": None if current == expected else "stale"}


def dispatch(method: str, params=None) -> dict:
    """Run one contract method and return its JSON-serialisable result."""
    params = _require_params(params)
    if method not in METHODS:
        raise ServiceError("method_not_found", f"unknown method '{method}'",
                           {"methods": list(METHODS)}, -32601)
    if method == "service.version":
        return _service_version()
    if method == "service.capabilities":
        return _service_capabilities()
    if method == "project.create":
        return _project_create(params)
    if method == "project.open":
        root = _root(params)
        return _project_open(root)
    if method == "project.validate":
        return _project_validate(params)
    if method == "project.save":
        return _project_save(params)
    if method == "assets.list":
        return _assets_list(params)
    if method == "assets.generate":
        return _assets_generate(params)
    if method == "grain.check":
        return _grain_check(params)
    if method == "grain.transpile":
        return _grain_transpile(params)
    if method == "check":
        return _check(params)
    if method == "build":
        return _build_or_run(params, run=False)
    if method == "run":
        return _build_or_run(params, run=True)
    if method == "targets":
        return {"targets": dict(TARGET_STATUS)}
    if method == "doctor":
        return _doctor()
    if method == "docs.generate":
        return _docs_generate()
    if method == "docs.check":
        return _docs_check()
    raise ServiceError("method_not_found", f"unknown method '{method}'",
                       rpc_code=-32601)  # pragma: no cover - METHODS guard


def _write(stream, message: dict) -> None:
    stream.write(json.dumps(message, separators=(",", ":")) + "\n")
    stream.flush()


def serve(stdin=None, stdout=None) -> int:
    """Serve newline-delimited JSON-RPC requests until stdin closes."""
    source = stdin if stdin is not None else sys.stdin
    sink = stdout if stdout is not None else sys.stdout
    for line in source:
        if not line.strip():
            continue
        request_id = None
        try:
            request = json.loads(line)
            if not isinstance(request, dict):
                raise ServiceError("invalid_request", "request must be an object",
                                   rpc_code=-32600)
            request_id = request.get("id")
            if request.get("jsonrpc") != "2.0":
                raise ServiceError("invalid_request", "jsonrpc must be '2.0'",
                                   rpc_code=-32600)
            method = request.get("method")
            if not isinstance(method, str):
                raise ServiceError("invalid_request", "method must be a string",
                                   rpc_code=-32600)
            with _stdout_to_stderr():
                result = dispatch(method, request.get("params"))
            _write(sink, {"jsonrpc": "2.0", "id": request_id, "result": result})
        except ServiceError as error:
            _write(sink, {"jsonrpc": "2.0", "id": request_id,
                          "error": error.as_dict()})
        except Exception as error:  # keep the protocol stream alive
            _write(sink, {"jsonrpc": "2.0", "id": request_id,
                          "error": {"code": -32603, "message": str(error),
                                    "data": {"type": type(error).__name__}}})
    return 0
