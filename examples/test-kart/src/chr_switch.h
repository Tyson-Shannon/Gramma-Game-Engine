#ifndef TEST_KART_CHR_SWITCH_H
#define TEST_KART_CHR_SWITCH_H

#include <stdbool.h>

#if defined(GRAMMA_TARGET_GB)
/* ROM bank 0 stays mapped, so the bank-probe setup runs from fixed code. */
#include <gb/gb.h>
#define GR_CHR_SWITCH_FIXED NONBANKED
#else
#define GR_CHR_SWITCH_FIXED
#endif

/*
 * Portable game-side helper for the example's two kart tilesets. On NES the
 * tilesets share tile indices in two CHR banks, so B flips the MMC3 sprite
 * pattern-table bank. On Game Boy and SMS, B stages a VRAM tile overlay from
 * the alternate tileset and patches a small part of the nametable. SMS also
 * verifies a sentinel in switchable ROM bank 2 when a Sega mapper is present.
 * Other targets have no banked art and ignore the toggle.
 */

void chr_switch_init(void) GR_CHR_SWITCH_FIXED;
void chr_switch_update(void);
bool chr_switch_probe_ok(void);

#endif /* TEST_KART_CHR_SWITCH_H */
