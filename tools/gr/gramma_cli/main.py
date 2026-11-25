"""Argument parsing and command implementations for the `gr` tool."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "pipeline"))

from gramma_pipeline import check_budget, format_report, generate, load_project  # noqa: E402
from gramma_pipeline.grain import GrainError, check_grain, transpile  # noqa: E402
from gramma_pipeline.budget import (  # noqa: E402
    GB_MAPPERS, NES_MAPPERS, gb_mapper_config, sms_mapper_config)
from gramma_pipeline.targets import TARGET_STATUS  # noqa: E402
from .cc65 import cc65_status, ensure_cc65  # noqa: E402
from .gbdk import ensure_gbdk, gbdk_status  # noqa: E402
from .sdl import sdl_environment, sdl_status  # noqa: E402
from .sms import ensure_sms, sms_status  # noqa: E402
from .template import create_project  # noqa: E402


def _execute(args: list[str], env: dict[str, str] | None = None) -> int:
    print("  $ " + " ".join(args))
    return subprocess.call(args, env=env)


def _find_project(explicit: str | None) -> Path:
    if explicit is not None:
        root = Path(explicit).resolve()
    elif Path.cwd().is_dir() and (Path.cwd() / "project.toml").is_file():
        root = Path.cwd()
    else:
        root = REPO / "examples" / "test-kart"
    if not (root / "project.toml").is_file():
        raise FileNotFoundError(f"no project.toml in {root}")
    return root


def _default_target(root: Path) -> str:
    with (root / "project.toml").open("rb") as handle:
        data = tomllib.load(handle)
    return data.get("project", {}).get("default_target", "pc")


def cmd_new(args: argparse.Namespace) -> int:
    directory = Path(args.directory).resolve()
    if directory.exists():
        print(f"error: {directory} already exists", file=sys.stderr)
        return 1
    name = args.name or directory.name
    create_project(directory, name)
    print(f"created {directory}")
    print(f"next: cd {directory} && gr run --target pc")
    return 0


def cmd_assets(args: argparse.Namespace) -> int:
    root = _find_project(args.project)
    target = args.target or _default_target(root)
    manifest = generate(root, target)
    print(f"generated {len(manifest['assets'])} assets for {target} in "
          f"{root / 'generated' / target}")
    return 0


def _mapper_override(args: argparse.Namespace) -> dict:
    override: dict = {}
    fields = (
        ("mapper", "nes.id"),
        ("prg_banks", "nes.prg_banks"),
        ("chr_banks", "nes.chr_banks"),
        ("gb_mapper", "gb.id"),
        ("gb_rom_banks", "gb.rom_banks"),
        ("gb_ram_banks", "gb.ram_banks"),
        ("sms_rom_banks", "sms.rom_banks"),
    )
    for attr, key in fields:
        value = getattr(args, attr, None)
        if value is not None:
            override[key] = value
    return override


def _grain_sources(root: Path) -> list[Path]:
    project = load_project(root)
    if not project.grain_sources:
        raise FileNotFoundError(
            "no Grain sources: add [grain] sources = [...] to project.toml "
            "or put a *.grain file in src/")
    return project.grain_sources


def cmd_grain(args: argparse.Namespace) -> int:
    root = _find_project(args.project)
    sources = _grain_sources(root)
    if args.out is not None:
        output = Path(args.out).resolve()
    else:
        target = args.target or _default_target(root)
        output = root / "generated" / target
    if not args.check:
        output.mkdir(parents=True, exist_ok=True)

    for source in sources:
        if not source.is_file():
            raise FileNotFoundError(f"Grain source not found: {source}")
        try:
            relative = source.resolve().relative_to(root.resolve())
        except ValueError:
            relative = source
        text = source.read_text(encoding="utf-8")
        try:
            if args.check:
                errors = check_grain(text, str(relative))
                if errors:
                    for error in errors:
                        print(error, file=sys.stderr)
                    return 1
                print(f"grain OK: {relative}")
                continue
            c_text, checker = transpile(text, str(relative))
            filename = "grain_" + re.sub(r"[^A-Za-z0-9_]", "_",
                                         source.stem) + ".c"
            destination = output / filename
            destination.write_text(c_text, encoding="utf-8")
            print(f"transpiled {relative} -> {destination}")
            print(f"  {len(checker.program.entities)} entities, "
                  f"{len(checker.program.scenes)} scenes")
        except GrainError as error:
            print(error, file=sys.stderr)
            return 1
    if not args.check:
        print(f"{len(sources)} Grain source(s) transpiled")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    root = _find_project(args.project)
    target = args.target or _default_target(root)
    project = load_project(root)
    manifest = generate(root, target, project, _mapper_override(args))
    errors = check_budget(project, target, manifest)
    print(format_report(errors, target))
    if args.verbose:
        for asset in manifest["assets"]:
            print(f"  {asset['name']:<12} {asset['kind']:<10} "
                  f"{asset.get('unique_tiles', 0):>4} tiles  "
                  f"{asset['rom_bytes']:>6} bytes")
    return 1 if errors else 0


def _nes_linker_config(share_dir: Path, builddir: Path,
                       prg_banks: int, chr_banks: int) -> Path | None:
    """Return a cc65 linker config for the requested NES layout.

    Fixed code stays in the final two 16 KB PRG banks. Earlier banks are
    data-only segments PRG0..PRG(n-3) and are emitted into the ROM before the
    code banks, so their file order matches their mapper bank numbers.
    """
    stock = share_dir / "cfg" / "nes.cfg"
    if prg_banks == 2 and chr_banks == 1:
        return stock

    if prg_banks == 2:
        updated, count = re.subn(
            r"(ROM2:\s+file = %O, start = \$0000, size = )\$2000",
            lambda m: m.group(1) + f"${chr_banks * 0x2000:04X}",
            stock.read_text(encoding="utf-8"))
        if count != 1:
            return None
        path = builddir / "nes.cfg"
        path.write_text(updated, encoding="utf-8")
        return path

    lines = [
        "SYMBOLS {",
        "    __STACKSIZE__: type = weak, value = $0300; # 3 pages stack",
        "}",
        "MEMORY {",
        "    ZP:     file = \"\", start = $0002, size = $001A, type = rw, define = yes;",
        "    HEADER: file = %O, start = $0000, size = $0010, fill = yes;",
    ]
    for bank in range(0, prg_banks - 2):
        lines.append(
            f"    PRG{bank}_MEM: file = %O, start = $8000, size = $4000, "
            "fill = yes, define = yes;")
    lines += [
        "    ROM0:   file = %O, start = $8000, size = $4000, fill = yes, define = yes;",
        "    ROMFIX: file = %O, start = $C000, size = $3FFA, fill = yes, define = yes;",
        "    ROMV:   file = %O, start = $FFFA, size = $0006, fill = yes;",
        f"    ROM2:   file = %O, start = $0000, size = ${chr_banks * 0x2000:04X}, fill = yes;",
        "    SRAM:   file = \"\", start = $0500, size = __STACKSIZE__, define = yes;",
        "    RAM:    file = \"\", start = $6000, size = $2000, define = yes;",
        "    RAMCODE_RAM: file = \"\", start = $7400, size = $0400, define = yes;",
        "}",
        "SEGMENTS {",
        "    ZEROPAGE: load = ZP,              type = zp;",
        "    HEADER:   load = HEADER,          type = ro;",
        "    STARTUP:  load = ROMFIX,          type = ro,  define   = yes;",
        "    LOWCODE:  load = ROMFIX,          type = ro,  optional = yes;",
        "    ONCE:     load = ROMFIX,          type = ro,  optional = yes;",
        "    CODE:     load = ROMFIX,          type = ro,  define   = yes;",
        "    RODATA:   load = ROM0,            type = ro,  define   = yes;",
    ]
    if prg_banks > 2:
        lines.append(
            "    CODE2:    load = ROM0,            type = ro,  define   = yes;")
    lines += [
        "    DATA:     load = ROMFIX, run = RAM, type = rw, define  = yes;",
        "    VECTORS:  load = ROMV,            type = rw;",
        "    CHARS:    load = ROM2,            type = rw;",
        "    RAMCODE:  load = ROM0, run = RAMCODE_RAM, type = rw, define = yes;",
        "    BSS:      load = RAM,             type = bss, define = yes;",
    ]
    for bank in range(0, prg_banks - 2):
        lines.append(
            f"    PRG{bank}: load = PRG{bank}_MEM, type = ro, optional = yes, "
            "define = yes;")
    lines += [
        "}",
        "FEATURES {",
        "    CONDES: type    = constructor,",
        "            label   = __CONSTRUCTOR_TABLE__,",
        "            count   = __CONSTRUCTOR_COUNT__,",
        "            segment = ONCE;",
        "    CONDES: type    = destructor,",
        "            label   = __DESTRUCTOR_TABLE__,",
        "            count   = __DESTRUCTOR_COUNT__,",
        "            segment = RODATA;",
        "    CONDES: type    = interruptor,",
        "            label   = __INTERRUPTOR_TABLE__,",
        "            count   = __INTERRUPTOR_COUNT__,",
        "            segment = RODATA,",
        "            import  = __CALLIRQ__;",
        "}",
        "",
    ]
    path = builddir / "nes.cfg"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _build_gb(root: Path, project, builddir: Path) -> tuple[int, Path | None]:
    gbdk, note = ensure_gbdk()
    if gbdk is None:
        print("error: GBDK-2020 unavailable; see `gr doctor`", file=sys.stderr)
        return 1, None
    print("  " + note)
    cfg = gb_mapper_config(project) if project is not None else gb_mapper_config(
        load_project(root))
    for error in cfg["errors"]:
        print(f"error: {error}", file=sys.stderr)
        return 1, None
    print(f"  GB mapper: {cfg['id']} "
          f"(ROM banks {cfg['rom_banks']}, SRAM banks {cfg['ram_banks']}, "
          f"cart type 0x{cfg['cart_type']:02x})")

    sources = sorted((REPO / "core" / "src").glob("*.c"))
    sources += [REPO / "targets" / "gb" / "src" / "gb_backend.c"]
    sources += sorted((root / "src").glob("*.c"))
    # Banked sources use #pragma bank and cannot fit a plain 32 KB ROM.
    if cfg["rom_banks"] > 2:
        sources += sorted((root / "src" / "gb").glob("*.c"))
    sources += sorted((root / "generated" / "gb").glob("*.c"))
    command = [str(gbdk / "bin" / "lcc"),
               "-o", str(builddir / "game.gb"),
               "-I" + str(REPO / "core" / "include"),
               "-I" + str(root / "generated" / "gb"),
               "-DGRAMMA_TARGET_GB",
               f"-Wl-yt0x{cfg['cart_type']:02x}",
               f"-Wl-yo{cfg['rom_banks']}",
               f"-DGR_GB_MAPPER={cfg['id_value']}",
               f"-DGR_GB_ROM_BANKS={cfg['rom_banks']}",
               f"-DGR_GB_RAM_BANKS={cfg['ram_banks']}"]
    if cfg["ram_banks"] > 0:
        command.append(f"-Wm-ya{cfg['ram_banks']}")
    command += [str(source) for source in sources]
    if _execute(command) != 0:
        return 1, None
    rom = builddir / "game.gb"
    if not rom.is_file():
        return 1, None
    print(f"  ROM: {rom} ({rom.stat().st_size} bytes)")
    return 0, rom


def _build_nes(root: Path, project, builddir: Path) -> tuple[int, Path | None]:
    toolchain, note = ensure_cc65()
    if toolchain is None:
        print("error: cc65 unavailable; see `gr doctor`", file=sys.stderr)
        return 1, None
    bin_dir, share_dir = toolchain
    print("  " + note)
    env = os.environ.copy()
    env["CC65_HOME"] = str(share_dir)

    sources = sorted((REPO / "core" / "src").glob("*.c"))
    sources += [REPO / "targets" / "nes" / "src" / "nes_backend.c"]
    sources += sorted((root / "src").glob("*.c"))
    sources += sorted((root / "src").glob("*.s"))
    sources += sorted((REPO / "targets" / "nes" / "src").glob("*.s"))
    generated = (root / "generated" / "nes")
    sources += sorted(generated.glob("*.s"))
    sources += sorted(generated.glob("*.c"))
    # Mapper config is validated by check_budget() before we get here.
    cfg = project.mapper.get("nes", {}) if project is not None else {}
    mapper_name = str(cfg.get("id", "nrom")).lower()
    mapper_id = NES_MAPPERS[mapper_name]
    prg_banks = int(cfg.get("prg_banks", 2))
    chr_banks = int(cfg.get("chr_banks", 1))
    code2_sources: list[Path] = []
    if prg_banks > 2:
        # Keep ROMFIX under 16 KB. The overlay queue is self-contained, so its
        # code can run from the switchable bank that startup maps at $8000.
        code2_sources = [REPO / "core" / "src" / "overlay.c"]
        sources = [source for source in sources if source not in code2_sources]
    print(f"  NES mapper: {mapper_name} (PRG banks {prg_banks}, CHR banks {chr_banks})")

    linker_cfg = _nes_linker_config(share_dir, builddir, prg_banks, chr_banks)
    if linker_cfg is None:
        print("error: could not generate the NES linker config",
              file=sys.stderr)
        return 1, None

    command = [str(bin_dir / "cl65"),
               "-t", "nes", "-C", str(linker_cfg),
               "-O", "-m", str(builddir / "game.map"),
               "-o", str(builddir / "game.nes"),
               "-I" + str(REPO / "core" / "include"),
               "-I" + str(root / "generated" / "nes"),
               "-DGRAMMA_TARGET_NES",
               "--asm-define", f"GR_NES_MAPPER={mapper_id}",
               "--asm-define", f"GR_NES_PRG_BANKS={prg_banks}",
               "--asm-define", f"GR_NES_CHR_BANKS={chr_banks}"]
    if prg_banks > 2:
        command += ["-DGR_NES_RAMCODE",
                    "--asm-define", "GR_NES_RAMCODE=1"]
        for source in code2_sources:
            obj = builddir / (source.stem + "-code2.o")
            compile_command = [
                str(bin_dir / "cl65"),
                "-t", "nes", "-c", "-O",
                "-I" + str(REPO / "core" / "include"),
                "-DGRAMMA_TARGET_NES",
                "-DGR_NES_RAMCODE",
                "--cc-args", "--code-name", "--cc-args", "CODE2",
                "-o", str(obj),
                str(source),
            ]
            if _execute(compile_command, env) != 0:
                return 1, None
            command.append(str(obj))
    command += [str(source) for source in sources]
    if _execute(command, env) != 0:
        return 1, None
    rom = builddir / "game.nes"
    if not rom.is_file():
        return 1, None
    print(f"  ROM: {rom} ({rom.stat().st_size} bytes)")
    return 0, rom


def _build_sms(root: Path, project, builddir: Path,
               gg: bool) -> tuple[int, Path | None]:
    toolchain, note = ensure_sms()
    if toolchain is None:
        print("error: SDCC/devkitSMS unavailable; see `gr doctor`",
              file=sys.stderr)
        return 1, None
    (bin_dir, _share_dir), (crt0, _smslib, peep_file) = toolchain
    print("  " + note)
    devkit = peep_file.parents[2]
    smslib_dir = peep_file.parents[1]
    library = smslib_dir / ("SMSlib_GG.lib" if gg else "SMSlib.lib")
    makesms = devkit / "tools" / "makesms" / "Linux" / "makesms"

    cfg = (sms_mapper_config(project) if project is not None else
           sms_mapper_config(load_project(root)))
    for error in cfg["errors"]:
        print(f"error: {error}", file=sys.stderr)
        return 1, None
    rom_banks = cfg["rom_banks"]
    print(f"  SMS mapper: {rom_banks} ROM banks ({rom_banks * 16} KB), "
          f"{'Game Gear' if gg else 'Master System'}")

    env = os.environ.copy()
    env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
    flags = [
        str(bin_dir / "sdcc"), "-c", "-mz80",
        "--peep-file", str(peep_file),
        "-I" + str(REPO / "core" / "include"),
        "-I" + str(smslib_dir / "src"),
        "-I" + str(root / "generated" / "sms"),
        "-DGRAMMA_TARGET_SMS",
        f"-DGR_SMS_ROM_BANKS={rom_banks}",
    ]
    if gg:
        flags.append("-DTARGET_GG")

    sources = sorted((REPO / "core" / "src").glob("*.c"))
    sources += [REPO / "targets" / "sms" / "src" / "sms_backend.c",
                REPO / "targets" / "sms" / "src" / "sms_header.c"]
    sources += sorted((root / "src").glob("*.c"))
    sources += sorted((root / "src" / "sms").glob("*.c"))
    sources += sorted((root / "generated" / "sms").glob("*.c"))

    objects: list[Path] = []
    bank_objects: list[tuple[int, Path]] = []
    for index, source in enumerate(sources):
        obj = builddir / f"sms-{index:02d}-{source.stem}.rel"
        command = flags + ["-o", str(obj), str(source)]
        match = re.fullmatch(r"bank(\d+)_.*\.c", source.name)
        if match is not None:
            bank = int(match.group(1))
            if bank < 2 or bank >= rom_banks:
                print(f"  note: skipping {source.name} (bank {bank} is not in "
                      f"the configured {rom_banks} ROM banks)")
                continue
            command += ["--constseg", f"BANK{bank}"]
            bank_objects.append((bank, obj))
        else:
            objects.append(obj)
        if _execute(command, env) != 0:
            return 1, None

    ihx = builddir / "game.ihx"
    link = [str(bin_dir / "sdcc"), "-o", str(ihx), "-mz80",
            "--no-std-crt0", "--data-loc", "0xC000"]
    for bank in range(2, rom_banks):
        link.append(f"-Wl-b_BANK{bank}=0x{0x8000 + bank * 0x10000:X}")
    link += [str(crt0)] + [str(obj) for obj in objects] + [str(library)]
    link += [str(obj) for _, obj in sorted(bank_objects)]
    print("  $ " + " ".join(link))
    linked = subprocess.run(link, env=env, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if linked.stdout:
        print(linked.stdout, end="")
    if linked.returncode != 0:
        # devkitSMS ships prebuilt libraries whose ABI markers predate SDCC
        # 4.5's sdcccall(1) default. sdld exits non-zero after those warnings
        # but still emits a valid IHX; real link errors are explicit.
        if ihx.is_file() and "?ASlink-Error-" not in linked.stdout:
            print("  note: SMSlib ABI warnings ignored; IHX was produced")
        else:
            return 1, None

    rom = builddir / ("game.gg" if gg else "game.sms")
    if _execute([str(makesms), str(ihx), str(rom)], env) != 0:
        return 1, None
    if not rom.is_file():
        return 1, None
    print(f"  ROM: {rom} ({rom.stat().st_size} bytes)")
    return 0, rom


def _build_pc(root: Path, project, builddir: Path, relative: Path,
              release: bool) -> tuple[int, Path | None]:
    env, note = sdl_environment(REPO)
    if note is None:
        print("error: SDL2 development files unavailable; see `gr doctor`",
              file=sys.stderr)
        return 1, None
    print("  " + note)

    setup = ["meson", "setup", str(builddir), str(REPO),
             f"-Dtarget=pc", f"-Dproject={relative}"]
    if env.get("SDL2_INCLUDE_DIR"):
        setup += [
            f"-Dsdl_include={env['SDL2_INCLUDE_DIR']}",
            f"-Dsdl_arch_include={env.get('SDL2_ARCH_INCLUDE_DIR', '')}",
            f"-Dsdl_library={env.get('SDL2_LIBRARY', '')}",
        ]
    if (builddir / "meson-info" / "meson-info.json").is_file():
        setup.append("--reconfigure")
    if release:
        setup.append("-Dbuildtype=release")
    if _execute(setup, env) != 0:
        return 1, None
    if _execute(["meson", "compile", "-C", str(builddir)], env) != 0:
        return 1, None
    executable = builddir / relative / "game"
    if not executable.is_file():
        candidates = list(builddir.rglob("game"))
        if candidates:
            executable = candidates[0]
        else:
            print(f"error: expected executable not found at {executable}",
                  file=sys.stderr)
            return 1, None
    return 0, executable


def _build(root: Path, target: str, release: bool,
           mapper_override: dict | None = None,
           gg: bool = False) -> tuple[int, Path | None]:
    project = load_project(root)
    manifest = generate(root, target, project, mapper_override)
    errors = check_budget(project, target, manifest)
    print(format_report(errors, target))
    if errors:
        return 1, None

    builddir = REPO / "build" / f"{project.name}-{target}"
    builddir.mkdir(parents=True, exist_ok=True)
    try:
        relative = root.resolve().relative_to(REPO.resolve())
    except ValueError:
        # Meson cannot subdir() outside its source tree. Stage external
        # projects inside the repo before configuring.
        staged = REPO / ".gr-projects" / project.name
        staged.mkdir(parents=True, exist_ok=True)
        # Generated files are owned by the pipeline; refresh them wholesale so
        # outputs from a previous target/layout cannot leak into this build.
        staged_generated = staged / "generated"
        if staged_generated.is_dir():
            shutil.rmtree(staged_generated)
        shutil.copytree(root, staged, dirs_exist_ok=True)
        root = staged
        relative = staged.relative_to(REPO)

    if target == "gb":
        return _build_gb(root, project, builddir)
    if target == "nes":
        return _build_nes(root, project, builddir)
    if target == "sms":
        return _build_sms(root, project, builddir, gg)
    if target == "pc":
        return _build_pc(root, project, builddir, relative, release)
    print(f"error: no build driver for target '{target}'", file=sys.stderr)
    return 1, None


def cmd_build(args: argparse.Namespace) -> int:
    root = _find_project(args.project)
    target = args.target or _default_target(root)
    status, _ = _build(root, target, args.release, _mapper_override(args),
                       getattr(args, "gg", False))
    return status


def cmd_run(args: argparse.Namespace) -> int:
    root = _find_project(args.project)
    target = args.target or _default_target(root)
    status, executable = _build(root, target, args.release,
                                _mapper_override(args), args.gg)
    if status != 0:
        return status
    if target != "pc":
        print(f"  {target} build ready: {executable}")
        if target == "nes":
            emulator = "Mesen or FCEUX"
        elif target == "sms":
            emulator = "Mesen or RetroArch"
        else:
            emulator = "SameBoy or Mesen"
        print(f"  launch it in an emulator, e.g. {emulator}")
        return 0
    env = os.environ.copy()
    if args.scale is not None:
        env["GRAMMA_SCALE"] = str(args.scale)
    if args.frames is not None:
        env["GRAMMA_TEST_FRAMES"] = str(args.frames)
    print(f"  running {executable.name} (target {target})")
    return subprocess.call([str(executable)], env=env)


def cmd_clean(args: argparse.Namespace) -> int:
    builddir = REPO / "build"
    if builddir.is_dir():
        shutil.rmtree(builddir)
        print(f"removed {builddir}")
    return 0


def cmd_targets(args: argparse.Namespace) -> int:
    for name, status in TARGET_STATUS.items():
        print(f"  {name:<10} {status}")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    print("Gramma doctor")
    print(f"  repo:      {REPO}")
    for tool in ("python3", "meson", "ninja", "gcc", "pkg-config"):
        location = shutil.which(tool)
        print(f"  {tool:<10} {location or 'MISSING'}")
    try:
        import PIL
        print(f"  Pillow:    {PIL.__version__}")
    except ImportError:
        print("  Pillow:    MISSING")
    print(f"  SDL2:      {sdl_status(REPO)}")
    print(f"  GBDK:      {gbdk_status()}")
    print(f"  cc65:      {cc65_status()}")
    print(f"  SMS/GG:    {sms_status()}")
    print("  Grain:     parser/typechecker/transpiler available")
    return 0


def _add_mapper_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--mapper", choices=sorted(NES_MAPPERS),
                        help="override [mapper.nes].id for this build/check")
    parser.add_argument("--prg-banks", type=int,
                        help="override the 16 KB PRG bank count")
    parser.add_argument("--chr-banks", type=int,
                        help="override the 8 KB CHR bank count")
    parser.add_argument("--gb-mapper", choices=sorted(GB_MAPPERS),
                        help="override [mapper.gb].id for this build/check")
    parser.add_argument("--gb-rom-banks", type=int,
                        help="override the 16 KB GB ROM bank count")
    parser.add_argument("--gb-ram-banks", type=int,
                        help="override the 8 KB GB SRAM bank count")
    parser.add_argument("--sms-rom-banks", type=int,
                        help="override the 16 KB SMS/Sega ROM bank count")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gr", description="Gramma: retro console game build tool")
    commands = parser.add_subparsers(dest="command")

    new = commands.add_parser("new", help="create a starter project")
    new.add_argument("directory")
    new.add_argument("--name")
    new.set_defaults(func=cmd_new)

    assets = commands.add_parser("assets", help="run the asset pipeline")
    assets.add_argument("--target")
    assets.add_argument("--project")
    assets.set_defaults(func=cmd_assets)

    for name, help_text in (("grain", "check or transpile Grain sources"),
                            ("transpile", "alias for 'grain'")):
        grain_cmd = commands.add_parser(name, help=help_text)
        grain_cmd.add_argument("--target")
        grain_cmd.add_argument("--project")
        grain_cmd.add_argument("--check", action="store_true",
                               help="parse and typecheck without emitting C")
        grain_cmd.add_argument("--out", help="write C into DIR instead of generated/<target>")
        grain_cmd.set_defaults(func=cmd_grain)

    check = commands.add_parser("check", help="run asset pipeline + budget checks")
    check.add_argument("--target")
    check.add_argument("--project")
    check.add_argument("-v", "--verbose", action="store_true")
    _add_mapper_args(check)
    check.set_defaults(func=cmd_check)

    build = commands.add_parser("build", help="generate assets and compile")
    build.add_argument("--target")
    build.add_argument("--project")
    build.add_argument("--release", action="store_true")
    build.add_argument("--gg", action="store_true",
                       help="build a Game Gear ROM instead of Master System")
    _add_mapper_args(build)
    build.set_defaults(func=cmd_build)

    run = commands.add_parser("run", help="build and launch")
    run.add_argument("--target")
    run.add_argument("--project")
    run.add_argument("--release", action="store_true")
    run.add_argument("--scale", type=int)
    run.add_argument("--frames", type=int,
                     help="auto-quit after N frames (headless testing)")
    run.add_argument("--gg", action="store_true",
                     help="build a Game Gear ROM instead of Master System")
    _add_mapper_args(run)
    run.set_defaults(func=cmd_run)

    clean = commands.add_parser("clean", help="remove build outputs")
    clean.set_defaults(func=cmd_clean)

    targets = commands.add_parser("targets", help="list supported targets")
    targets.set_defaults(func=cmd_targets)

    doctor = commands.add_parser("doctor", help="check local toolchains")
    doctor.set_defaults(func=cmd_doctor)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if hasattr(args, "func"):
        try:
            return args.func(args)
        except GrainError as error:
            print(error, file=sys.stderr)
            return 1
        except (FileNotFoundError, ValueError) as error:
            print(f"error: {error}", file=sys.stderr)
            return 1
    parser.print_help()
    return 0
