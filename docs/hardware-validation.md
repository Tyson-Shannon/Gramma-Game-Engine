# Physical hardware validation

CI runs rendered-frame emulators for Game Boy (PyBoy) and NES (`nes-py`). SMS/GG
currently has structural ROM checks instead: header, region/size byte, checksum
and bank sentinels. Physical hardware checks are **deferred for now**: this
checklist is kept for a later pass and does not block SMS/GG or Phase 3 work.
Automated checks are the current verification gate; skipped is not the same as
passed.

When hardware testing resumes, a person must run the checks below and record the
results here. The ROMs are built from `examples/test-kart`; press **B** to
exercise banked art. Do not claim a hardware result until it has been observed on
real silicon.

## Requirements

| Console | Suggested hardware | Notes |
|---|---|---|
| Game Boy / GBC | flash cart with MBC1 support | The default build is a 64 KB MBC1 ROM with no SRAM. An MBC3/MBC5 cart only helps if you rebuild with `--gb-mapper mbc3/mbc5`. |
| NES | flash cart or powerPak-style mapper supporting MMC3 with 2x16 KB PRG and 2x8 KB CHR | The default build is MMC3; a four-bank PRG build needs a mapper that handles 64 KB PRG and NES 2.0-style size metadata. |
| Master System / Game Gear | flash cart with Sega slot-2 mapper support (at least 64 KB) | The default SMS/GG build is 64 KB with four 16 KB banks; a two-bank fixed layout is also built in CI. |

Build the exact ROMs under test and record their hashes so a hardware observation
can be tied to a build:

```sh
./tools/gr/gr build --target gb
sha256sum build/test-kart-gb/game.gb

./tools/gr/gr build --target nes
sha256sum build/test-kart-nes/game.nes

./tools/gr/gr build --target nes --prg-banks 4
sha256sum build/test-kart-nes/game.nes

./tools/gr/gr build --target sms
sha256sum build/test-kart-sms/game.sms

./tools/gr/gr build --target sms --gg
sha256sum build/test-kart-sms/game.gg
```

## Game Boy MBC checklist

1. Load the default `game.gb`. Confirm the title screen/kart scene renders with
   four shades and no missing or garbled tiles.
2. Press B once. The alternate kart tiles should appear and part of the
   nametable should change, matching the 384-pixel difference seen in PyBoy.
3. Press B again. The scene should return exactly to the original art. Repeat
   several times to catch a one-way switch or a bank that is left mapped while
   an interrupt runs.
4. With a debug cart/probe, read the switchable ROM window at `$4000` while
   bank 2 is selected. The first three bytes of the `BANKED` sentinel are
   `3e 5a c9`; calling it should return `0x5a`. This is the hardware equivalent
   of the CI header check and does not require patching a temporary ROM.
5. Confirm fixed code remains mapped at `$0000-$3FFF` throughout: input, audio
   and rendering must not lock up while the switchable window changes.
6. For SRAM layouts built with `--gb-ram-banks > 0`, verify that saving/loading
   a game does not alter the visible ROM bank.

Record: console model, flash cart, ROM hash, whether the sentinel returned
`0x5a`, and whether the B toggle changed/reverted the image.

## NES CHR checklist

1. Load the default MMC3 ROM. Confirm sprites and background render, with the
   kart using the sprite pattern table.
2. Press B. The kart art changes from bank 0 to bank 1 while the background is
   unchanged (264 sprite pixels in the emulator). Press B again and confirm it
   returns exactly.
3. Move with the controller during rapid B presses. Input and music must keep
   working, since the switch modifies the sprite pattern table through MMC3 R2.
4. Check for palette or nametable artifacts during scrolling: the custom NMI
   writes `$2005` every vblank, and CHR swaps must not corrupt that state.

## NES PRG checklist

1. Load the four-bank MMC3 ROM (`--prg-banks 4`). Confirm it boots and renders
   the same scene as the two-bank build; the first byte of PRG0 is `0xa5`, read
   through the RAM-resident `gr_nes_prg_read()` helper.
2. Trigger the same B toggle and confirm sprite art still switches from bank 0
   to bank 1. This verifies that placing `overlay.c` in the switchable code bank
   did not break execution from `ROMFIX`.
3. Build 8- and 16-bank variants if the cart supports them. For the 16-bank ROM,
   confirm the NES 2.0 header size MSB (`0x10` in byte 8) does not prevent boot.
4. Exercise music/SFX while switching CHR banks; PRG windows hold running code,
   so the game must use the RAM-resident PRG reader instead of switching the
   window that contains the caller.

Record: console model/revision, flash cart and mapper support, PRG/CHR bank
counts, ROM hash, and observations for each numbered check.

## NES mirroring, palettes and DMC checklist

1. Build NROM with `--mirroring four-screen`, verify header byte 6 is `0x0a`,
   and place distinct content in all four nametables; each must render without
   bleeding into another. Horizontal (`0x42` on MMC3) and vertical (`0x43` on
   MMC3) must show the expected two-table mirroring.
2. With a split `gr_bg.palette_map`, confirm a single nametable shows all four
   background palette regions at 16x16-tile boundaries and that coarse
   scrolling refreshes attributes without color tearing.
3. Trigger a WAV SFX with `gr_sfx_def.dmc` set. Confirm audible sample playback
   at the configured rate, that the loop bit repeats only when requested, and
   that music/tones continue afterward.

This checklist is **deferred**: none of these three checks has run on hardware,
and the current emulator smoke does not cover the rendered palette/nametable or
audible DMC results. Record results in the table below only after a real pass.

## SMS / GG checklist

1. Load the four-bank `game.sms`. Confirm the SEGA header is accepted by the
   BIOS and the 256x192 scene renders with the expected 16-color palettes.
2. Press B. The alternate kart art should appear in the sprite tile half and a
   small nametable patch should change; press again to restore the original.
3. With a mapper-capable cart/probe, read `$8000-$BFFF` while bank 2 is selected.
   The first bytes are `5a a5 01 02`; bank 3 starts `3c c3 03 04`. The example
   shifts its scroll by 8 pixels when the bank-2 probe returns `0x5a`.
4. Confirm fixed code in banks 0/1 keeps running while slot 2 changes: input,
   music and rendering must not lock up after repeated B presses.
5. Build the Game Gear variant with `--gg` and repeat the visual check on real
   Game Gear hardware, including the separate START button mapping.
6. Build `--sms-rom-banks 2` and confirm the fixed 32 KB layout still boots and
   ignores banked probes without writing the mapper register.

Record: console/revision, flash cart and mapper support, bank count, ROM hash,
the byte read from bank 2 and whether the B toggle changed/reverted the image.

## Results log

| Date | Tester | Console + cart | ROM hash | Result |
|---|---|---|---|---|
| _deferred_ | _deferred_ | _deferred_ | _deferred_ | Physical hardware checks skipped for now; emulator CI is the active gate. |

When a check passes, replace the deferred row with the actual date, tester,
hardware, hash and a short note. Record failures here too, with the observed
symptoms, so emulator-only claims are never mistaken for hardware verification.
