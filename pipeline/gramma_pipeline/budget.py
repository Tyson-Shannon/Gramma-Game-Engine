"""Build-time budget enforcement. Returns human-readable error strings."""

from __future__ import annotations

from .project import Project
from .targets import PROFILES

NES_MAPPERS = {"nrom": 0, "mmc1": 1, "mmc3": 4}
GB_MAPPERS = {"none": 0x00, "mbc1": 0x01, "mbc3": 0x11, "mbc5": 0x19}
GB_MAX_ROM_BANKS = {"none": 2, "mbc1": 32, "mbc3": 128, "mbc5": 128}
GB_MAX_RAM_BANKS = 16
# SMS/Sega mapper: banks 0/1 are fixed, banks 2..N-1 map into $8000-$BFFF.
SMS_MIN_ROM_BANKS = 2
SMS_MAX_ROM_BANKS = 64
SMS_SIZE_CODE = {2: 0xc, 4: 0xe, 8: 0xf, 16: 0x0, 32: 0x1, 64: 0x2}
# PRG banks are 16 KB. MMC1/MMC3 keep code in the final two banks and place
# data-only extra banks in generated linker segments PRG2...PRGn.
MIN_PRG_BANKS = 2
MAX_PRG_BANKS = 16
# 8 KB CHR banks. The standard cc65 layout is one bank; larger counts use a
# generated linker config with a proportionally larger ROM2 segment.
MAX_CHR_BANKS = 16
CHR_TILES_PER_TABLE = 256


def _is_power_of_two(value: int) -> bool:
    return value > 0 and (value & (value - 1)) == 0


NES_MIRRORINGS = {
    "horizontal": 0,
    "vertical": 1,
    "four-screen": 8,
}


def nes_mapper_config(project: Project) -> dict:
    """Return the validated NES cart layout used by `gr check`/`gr build`.

    `mirror_bit` is the iNES header mirroring field: 0 horizontal, 1 vertical,
    8 four-screen. Four-screen needs a board with four physical nametables, so
    it is only allowed on NROM; MMC1/MMC3 boards use their mirroring registers.
    """
    cfg = project.mapper.get("nes", {})
    errors: list[str] = []
    mapper_id = str(cfg.get("id", "nrom")).lower()
    if mapper_id not in NES_MAPPERS:
        supported = ", ".join(sorted(NES_MAPPERS))
        errors.append(
            f"mapper: unknown NES mapper '{mapper_id}' "
            f"(supported: {supported})")
        mapper_id = "nrom"

    banks = {"prg_banks": MIN_PRG_BANKS, "chr_banks": 1}
    for key in ("prg_banks", "chr_banks"):
        if key not in cfg:
            continue
        try:
            banks[key] = int(cfg[key])
        except (TypeError, ValueError):
            errors.append(f"mapper: {key} must be an integer")
            continue
        if not _is_power_of_two(banks[key]):
            errors.append(f"mapper: {key} must be a power of two, got {banks[key]}")

    if _is_power_of_two(banks["prg_banks"]):
        if banks["prg_banks"] < MIN_PRG_BANKS:
            errors.append(f"mapper: prg_banks must be at least {MIN_PRG_BANKS}")
        if banks["prg_banks"] > MAX_PRG_BANKS:
            errors.append(
                f"mapper: prg_banks={banks['prg_banks']} exceeds the maximum "
                f"{MAX_PRG_BANKS} (256 KB PRG)")
        if banks["prg_banks"] > MIN_PRG_BANKS and mapper_id == "nrom":
            errors.append("mapper: nrom supports only two 16 KB PRG banks")
    if _is_power_of_two(banks["chr_banks"]):
        if banks["chr_banks"] > MAX_CHR_BANKS:
            errors.append(
                f"mapper: chr_banks={banks['chr_banks']} exceeds the maximum "
                f"{MAX_CHR_BANKS} (128 KB CHR)")
        if banks["chr_banks"] > 1 and mapper_id == "nrom":
            errors.append("mapper: nrom supports only one 8 KB CHR bank")

    mirroring = str(cfg.get("mirroring", "vertical")).lower()
    if mirroring not in NES_MIRRORINGS:
        errors.append(
            f"mapper: unknown NES mirroring '{mirroring}' "
            f"(supported: {', '.join(sorted(NES_MIRRORINGS))})")
        mirroring = "vertical"
    if mirroring == "four-screen" and mapper_id != "nrom":
        errors.append(
            "mapper: four-screen mirroring requires a four-nametable NROM "
            "board; MMC1/MMC3 only support vertical/horizontal")

    return {
        "errors": errors,
        "id": mapper_id,
        "id_value": NES_MAPPERS[mapper_id],
        "prg_banks": banks["prg_banks"],
        "chr_banks": banks["chr_banks"],
        "mirroring": mirroring,
        "mirror_bit": NES_MIRRORINGS[mirroring],
    }


def _nes_mapper_errors(project: Project) -> tuple[list[str], int]:
    cfg = nes_mapper_config(project)
    return cfg["errors"], cfg["chr_banks"]


def gb_mapper_config(project: Project) -> dict:
    """Return the validated Game Boy cart layout used by `gr check`/`gr build`."""
    cfg = project.mapper.get("gb", {})
    mapper = str(cfg.get("id", "none")).lower()
    errors: list[str] = []
    if mapper not in GB_MAPPERS:
        errors.append(
            f"mapper: unknown Game Boy mapper '{mapper}' "
            f"(supported: {', '.join(sorted(GB_MAPPERS))})")
        mapper = "none"

    values = {"rom_banks": 2, "ram_banks": 0}
    for key in values:
        if key not in cfg:
            continue
        try:
            values[key] = int(cfg[key])
        except (TypeError, ValueError):
            errors.append(f"mapper: gb {key} must be an integer")
            continue
        if values[key] < 0:
            errors.append(f"mapper: gb {key} must not be negative")

    rom_banks = values["rom_banks"]
    ram_banks = values["ram_banks"]
    if mapper == "none":
        if rom_banks != 2 or ram_banks != 0:
            errors.append("mapper: plain ROM supports only 2 banks and no SRAM")
    else:
        if rom_banks < 2 or not _is_power_of_two(rom_banks):
            errors.append(
                f"mapper: gb rom_banks must be a power of two >= 2, "
                f"got {rom_banks}")
        elif rom_banks > GB_MAX_ROM_BANKS[mapper]:
            errors.append(
                f"mapper: gb rom_banks={rom_banks} exceeds the "
                f"{mapper} maximum {GB_MAX_ROM_BANKS[mapper]}")
        if ram_banks and not _is_power_of_two(ram_banks):
            errors.append(
                f"mapper: gb ram_banks must be 0 or a power of two, "
                f"got {ram_banks}")
        elif ram_banks > GB_MAX_RAM_BANKS:
            errors.append(
                f"mapper: gb ram_banks={ram_banks} exceeds the maximum "
                f"{GB_MAX_RAM_BANKS}")

    if mapper == "mbc1" and ram_banks > 4:
        errors.append("mapper: mbc1 supports at most 4 SRAM banks")
    if mapper == "mbc3" and ram_banks > 4:
        errors.append("mapper: mbc3 supports at most 4 SRAM banks")

    cart_type = GB_MAPPERS[mapper]
    if mapper == "mbc1" and ram_banks:
        cart_type = 0x02           # ROM + MBC1 + RAM
    elif mapper == "mbc3" and ram_banks:
        cart_type = 0x12           # ROM + MBC3 + RAM
    elif mapper == "mbc5" and ram_banks:
        cart_type = 0x1A           # ROM + MBC5 + RAM

    return {
        "errors": errors,
        "id": mapper,
        "id_value": {"none": 0, "mbc1": 1, "mbc3": 3, "mbc5": 5}[mapper],
        "rom_banks": rom_banks,
        "ram_banks": ram_banks,
        "cart_type": cart_type,
    }


def sms_mapper_config(project: Project) -> dict:
    """Return the validated Sega slot-2 ROM layout used by `gr check`/`build`."""
    cfg = project.mapper.get("sms", {})
    errors: list[str] = []
    try:
        rom_banks = int(cfg.get("rom_banks", SMS_MIN_ROM_BANKS))
    except (TypeError, ValueError):
        rom_banks = SMS_MIN_ROM_BANKS
        errors.append("mapper: sms rom_banks must be an integer")

    if not _is_power_of_two(rom_banks):
        errors.append(
            f"mapper: sms rom_banks must be a power of two, got {rom_banks}")
    elif rom_banks < SMS_MIN_ROM_BANKS:
        errors.append(f"mapper: sms rom_banks must be at least {SMS_MIN_ROM_BANKS}")
    elif rom_banks > SMS_MAX_ROM_BANKS:
        errors.append(
            f"mapper: sms rom_banks={rom_banks} exceeds the maximum "
            f"{SMS_MAX_ROM_BANKS} (1 MB)")

    return {
        "errors": errors,
        "rom_banks": rom_banks,
        "size_code": SMS_SIZE_CODE.get(rom_banks, 0xc),
    }


def _violation(code: str, category: str, message: str, target: str,
               asset: str | None = None) -> dict:
    """Return the stable JSON form shared by CLI, GUI and LSP-style clients."""
    result = {
        "code": code,
        "category": category,
        "severity": "error",
        "target": target,
        "message": message,
    }
    if asset is not None:
        result["asset"] = asset
    return result


def check_budget_detailed(project: Project, target: str,
                          manifest: dict) -> list[dict]:
    """Like :func:`check_budget`, but with codes, categories and asset names."""
    violations: list[dict] = []
    profile = PROFILES.get(target)
    if profile is None:
        return [_violation("budget.unknown_target", "target",
                           f"unknown target '{target}'", target)]

    def add(code: str, category: str, message: str,
            asset: str | None = None) -> None:
        violations.append(_violation(code, category, message, target, asset))

    limits = dict(profile)
    for key, value in project.budgets.get(target, {}).items():
        if key in limits:
            limits[key] = int(value)

    if target == "nes":
        for message in nes_mapper_config(project)["errors"]:
            add("budget.mapper", "mapper", message)
        for asset in project.audio:
            if not 0 <= asset.dmc_rate <= 15:
                add("budget.dmc_rate", "audio",
                    f"{asset.name}: dmc_rate {asset.dmc_rate} is outside 0..15",
                    asset.name)
    if target == "gb":
        for message in gb_mapper_config(project)["errors"]:
            add("budget.mapper", "mapper", message)
    if target == "sms":
        sms = sms_mapper_config(project)
        for message in sms["errors"]:
            add("budget.mapper", "mapper", message)
        if sms["rom_banks"] * 16 > limits["rom_kb"]:
            add("budget.mapper", "mapper",
                f"mapper: sms {sms['rom_banks']} ROM banks need "
                f"{sms['rom_banks'] * 16} KB, budgets.sms.rom_kb is "
                f"{limits['rom_kb']}")

    for asset in manifest["assets"]:
        name = asset["name"]
        if asset["kind"] in ("audio", "music"):
            continue
        if asset["bpp"] not in profile["bpp"]:
            add("budget.asset_bpp", "asset",
                f"{name}: {asset['bpp']}bpp is not supported on {target} "
                f"(supported: {', '.join(str(b) for b in sorted(profile['bpp']))})",
                name)
        if asset["palette_colors"] > limits["palette_colors"]:
            add("budget.asset_palette", "asset",
                f"{name}: palette uses {asset['palette_colors']} colors, "
                f"{target} allows {limits['palette_colors']}", name)
        if (asset["kind"] in ("background", "map") and
                limits["nametable_tiles"] is not None and
                asset["tile_count"] > limits["nametable_tiles"]):
            add("budget.asset_nametable", "asset",
                f"{name}: {asset['kind']} uses {asset['tile_count']} tiles, "
                f"{target} nametable limit is {limits['nametable_tiles']}", name)

    unique_tiles = sum(asset["unique_tiles"] for asset in manifest["assets"])
    if unique_tiles > limits["vram_tiles"]:
        add("budget.vram", "vram",
            f"VRAM: {unique_tiles} unique tiles exceeds {target} budget "
            f"of {limits['vram_tiles']}")

    if manifest["declared_sprites"] > limits["sprites"]:
        add("budget.sprites", "sprite",
            f"sprites: {manifest['declared_sprites']} live sprites exceeds "
            f"{target} budget of {limits['sprites']}")
    if (manifest["declared_sprites"] > limits["sprites_per_line"] and
            limits["sprites_per_line"] < limits["sprites"]):
        add("budget.sprites_per_line", "sprite",
            f"sprites: {manifest['declared_sprites']} sprites may exceed the "
            f"{target} per-scanline limit of {limits['sprites_per_line']}")

    rom_bytes = manifest["totals"]["rom_bytes"]
    rom_limit = limits["rom_kb"] * 1024
    if rom_bytes > rom_limit:
        add("budget.rom", "rom",
            f"ROM: {rom_bytes} bytes of asset data exceeds {target} budget "
            f"of {rom_limit} bytes (code not yet counted)")

    if target == "nes":
        mapper = nes_mapper_config(project)
        chr_banks = mapper["chr_banks"]
        if chr_banks > 0:
            used: dict[int, int] = {}
            for asset in manifest["assets"]:
                if asset["kind"] == "audio":
                    continue
                name = asset["name"]
                bank = asset.get("chr_bank", 0)
                if bank < 0 or bank >= chr_banks:
                    add("budget.chr_bank", "mapper",
                        f"{name}: chr_bank {bank} is outside the "
                        f"configured {chr_banks} CHR banks", name)
                    continue
                tile = asset.get("chr_tile")
                if tile is not None and tile < 0:
                    add("budget.chr_tile", "mapper",
                        f"{name}: chr_tile {tile} must not be negative", name)
                elif (tile is not None and
                      tile + asset["unique_tiles"] > CHR_TILES_PER_TABLE):
                    add("budget.chr_tile", "mapper",
                        f"{name}: chr_tile {tile} with "
                        f"{asset['unique_tiles']} tiles exceeds the "
                        f"{CHR_TILES_PER_TABLE}-tile pattern table", name)
                used[bank] = used.get(bank, 0) + asset["unique_tiles"]
            for bank, tiles in used.items():
                if tiles > CHR_TILES_PER_TABLE:
                    add("budget.chr_bank", "mapper",
                        f"CHR bank {bank}: {tiles} unique tiles exceed the "
                        f"{CHR_TILES_PER_TABLE}-tile pattern table")
    return violations


def check_budget(project: Project, target: str, manifest: dict) -> list[str]:
    """Return human-readable error strings for the CLI and existing callers."""
    return [item["message"] for item in check_budget_detailed(
        project, target, manifest)]


def format_report(errors: list[str], target: str) -> str:
    if not errors:
        return f"budget OK for {target}"
    return "\n".join(f"error: {error}" for error in errors)
