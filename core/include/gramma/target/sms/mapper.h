#ifndef GRAMMA_SMS_MAPPER_H
#define GRAMMA_SMS_MAPPER_H

/*
 * Opt-in SMS slot-2 ROM banking. This header is intentionally not included by
 * gramma.h. Bank 0 and bank 1 are fixed at $0000-$7FFF; the 16 KB slot at
 * $8000-$BFFF is switched by writing the Sega mapper register at $FFFF.
 *
 * Logical banks follow the physical ROM bank numbers used by devkitSMS, so
 * bank 2 is the first switchable bank. The build injects GR_SMS_ROM_BANKS from
 * [mapper.sms] in project.toml.
 */

#include <gramma/bank.h>
#include <gramma/types.h>

#ifdef __cplusplus
extern "C" {
#endif

#define GR_SMS_MIN_ROM_BANKS 2u
#define GR_SMS_MAX_ROM_BANKS 64u
#define GR_SMS_DEFAULT_BANK  2u

typedef void (*gr_sms_bank_write_fn)(uint16_t bank, void *user);

typedef struct {
    uint8_t              rom_banks;
    gr_sms_bank_write_fn write;
    void                *user;
    gr_bank_set          rom;
} gr_sms_mapper_state;

/* Initialise a mapper state. A two-bank ROM has no switchable slot. */
gr_result gr_sms_mapper_init(gr_sms_mapper_state *state, uint8_t rom_banks,
                             gr_sms_bank_write_fn write, void *user);

/* Runtime mapper installed by the SMS backend from the build-time layout. */
gr_result gr_sms_mapper_runtime_init(uint8_t rom_banks,
                                     gr_sms_bank_write_fn write, void *user);
uint8_t   gr_sms_mapper_rom_bank_count(void);
gr_bank_set *gr_sms_mapper_rom_banks(void);

#ifdef __cplusplus
}
#endif

#endif /* GRAMMA_SMS_MAPPER_H */
