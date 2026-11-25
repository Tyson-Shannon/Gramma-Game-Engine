"""Hardware budgets and pixel formats for each supported backend.

These are intentionally conservative. A build fails here instead of producing
a ROM that only breaks on hardware. Values can be overridden per project in
project.toml under [budgets.<target>].
"""

PROFILES = {
    "pc": {
        "packing": "chunky",
        "bpp": {1, 2, 4, 8},
        "palette_colors": 16,
        "vram_tiles": 4096,
        "sprites": 64,
        "sprites_per_line": 64,
        "rom_kb": 2048,
        "nametable_tiles": None,
    },
    "gb": {
        "packing": "planar",
        "bpp": {1, 2},
        "palette_colors": 4,
        "vram_tiles": 384,
        "sprites": 40,
        "sprites_per_line": 10,
        "rom_kb": 32,
        "nametable_tiles": 1024,
    },
    "nes": {
        "packing": "planar",
        "bpp": {1, 2},
        "palette_colors": 4,
        "vram_tiles": 512,
        "sprites": 64,
        "sprites_per_line": 8,
        "rom_kb": 32,
        "nametable_tiles": 960,
    },
    "sms": {
        "packing": "planar",
        "bpp": {1, 2, 4},
        "palette_colors": 16,
        "vram_tiles": 512,
        "sprites": 64,
        "sprites_per_line": 8,
        "rom_kb": 64,
        "nametable_tiles": 1024,
    },
    "genesis": {
        "packing": "chunky",
        "bpp": {4},
        "palette_colors": 16,
        "vram_tiles": 1536,
        "sprites": 80,
        "sprites_per_line": 20,
        "rom_kb": 4096,
        "nametable_tiles": None,
    },
    "gba": {
        "packing": "chunky",
        "bpp": {4, 8},
        "palette_colors": 256,
        "vram_tiles": 1024,
        "sprites": 128,
        "sprites_per_line": 128,
        "rom_kb": 32768,
        "nametable_tiles": None,
    },
    "snes": {
        "packing": "planar",
        "bpp": {2, 4, 8},
        "palette_colors": 256,
        "vram_tiles": 1024,
        "sprites": 128,
        "sprites_per_line": 32,
        "rom_kb": 4096,
        "nametable_tiles": 2048,
    },
}

TARGET_STATUS = {
    "pc": "working (SDL2 simulator)",
    "gb": "working (GBDK-2020)",
    "nes": "working (cc65 NROM/MMC1/MMC3)",
    "sms": "working (SDCC + devkitSMS)",
    "genesis": "planned (Phase 3)",
    "gba": "planned (Phase 3)",
    "snes": "planned (Phase 4)",
}
