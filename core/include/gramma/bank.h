#ifndef GRAMMA_BANK_H
#define GRAMMA_BANK_H

/*
 * Opt-in bank abstraction. This header is intentionally NOT included by
 * gramma.h: most games never switch banks, and the portable base API stays a
 * lowest-common-denominator contract. Target-specific headers (for example
 * gramma/target/nes/mapper.h) describe which bank sets a mapper exposes.
 */

#include <gramma/types.h>

#ifdef __cplusplus
extern "C" {
#endif

#define GR_BANK_MAX_SLOTS 8u

typedef void (*gr_bank_write_fn)(uint8_t slot, uint16_t bank, void *user);

typedef struct {
    uint8_t          slot_count;
    uint16_t         current[GR_BANK_MAX_SLOTS];
    gr_bank_write_fn write;   /* NULL for software-only bank sets */
    void            *user;
} gr_bank_set;

/* Initialise a logical bank set. slot_count must be <= GR_BANK_MAX_SLOTS. */
gr_result gr_bank_set_init(gr_bank_set *set, uint8_t slot_count,
                           gr_bank_write_fn write, void *user);

/* Select a bank in one slot; calls the backend writer when one is installed. */
gr_result gr_bank_select(gr_bank_set *set, uint8_t slot, uint16_t bank);

/* Query helpers. Invalid slots read as bank 0. */
uint8_t   gr_bank_slots(const gr_bank_set *set);
uint16_t  gr_bank_current(const gr_bank_set *set, uint8_t slot);

/* Two-bank game helper --------------------------------------------------- */

/*
 * Games often keep two versions of the same tile indices in different banks
 * and flip between them during play. gr_bank_switch caches that pair so game
 * code does not need to remember which raw bank is currently selected.
 *
 * The bank values are target-specific. On NES they are mapper register values,
 * so use GR_NES_CHR_BANK4(n) for 8 KB asset banks.
 */
typedef struct {
    gr_bank_set *set;
    uint8_t      slot;
    uint16_t     bank_a;
    uint16_t     bank_b;
    bool         alternate;
} gr_bank_switch;

gr_result gr_bank_switch_init(gr_bank_switch *sw, gr_bank_set *set,
                              uint8_t slot, uint16_t bank_a, uint16_t bank_b);
/* Select the other bank and return the new value, or 0 on error. */
uint16_t  gr_bank_switch_toggle(gr_bank_switch *sw);
/* Select the first bank. Useful when loading a scene. */
gr_result gr_bank_switch_reset(gr_bank_switch *sw);

#ifdef __cplusplus
}
#endif

#endif /* GRAMMA_BANK_H */
