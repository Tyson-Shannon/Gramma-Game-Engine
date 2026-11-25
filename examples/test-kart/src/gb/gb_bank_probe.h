#ifndef TEST_KART_GB_BANK_PROBE_H
#define TEST_KART_GB_BANK_PROBE_H

#include <gb/gb.h>
#include <stdint.h>

/* Located in ROM bank 2 by gb_bank_probe.c. GBDK's BANKED call helper lives in
 * fixed code and restores the previous ROM bank on return. */
uint8_t gb_bank_probe_read(void) BANKED;

#endif /* TEST_KART_GB_BANK_PROBE_H */
