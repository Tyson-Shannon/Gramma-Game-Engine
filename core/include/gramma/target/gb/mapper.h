#ifndef GRAMMA_TARGET_GB_MAPPER_H
#define GRAMMA_TARGET_GB_MAPPER_H

/*
 * Opt-in Game Boy MBC extension. A plain 32 KB ROM has no switchable banks;
 * MBC1/MBC3/MBC5 expose one 16 KB ROM window at $4000-$7FFF and, when the
 * cartridge has SRAM, one 8 KB RAM window at $A000-$BFFF. See docs/banking.md.
 */

#include <gramma/bank.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    GR_GB_MAPPER_NONE = 0,
    GR_GB_MAPPER_MBC1 = 1,
    GR_GB_MAPPER_MBC3 = 3,
    GR_GB_MAPPER_MBC5 = 5
} gr_gb_mapper;

/* The backend (or a unit test) supplies the real hardware writes. */
typedef void (*gr_gb_bank_write_fn)(uint8_t kind, uint16_t bank, void *user);

#define GR_GB_BANK_ROM 0u
#define GR_GB_BANK_RAM 1u

typedef struct {
    gr_gb_mapper       id;
    uint8_t            rom_banks;   /* 16 KB banks, including fixed bank 0 */
    uint8_t            ram_banks;   /* 8 KB banks, 0 when no SRAM */
    gr_bank_set        rom;
    gr_bank_set        ram;
    gr_gb_bank_write_fn write;
    void              *user;
} gr_gb_mapper_state;

/* Initialise an MBC state with an injected writer. Bank 0 is fixed, so the ROM
 * set contains physical banks 1..rom_banks-1. The RAM set contains
 * 0..ram_banks-1 and has zero slots when the cartridge has no SRAM. */
gr_result gr_gb_mapper_init(gr_gb_mapper_state *state, gr_gb_mapper id,
                            uint8_t rom_banks, uint8_t ram_banks,
                            gr_gb_bank_write_fn write, void *user);

/* Runtime mapper owned by the Game Boy backend. `gr_init()` initialises it
 * from the build-time [mapper.gb] configuration. */
gr_result gr_gb_mapper_runtime_init(gr_gb_mapper id, uint8_t rom_banks,
                                    uint8_t ram_banks,
                                    gr_gb_bank_write_fn write, void *user);
gr_gb_mapper gr_gb_mapper_runtime_id(void);
uint8_t   gr_gb_mapper_rom_bank_count(void);
uint8_t   gr_gb_mapper_ram_bank_count(void);
gr_bank_set *gr_gb_mapper_rom_banks(void);
gr_bank_set *gr_gb_mapper_ram_banks(void);

/* Build-time defaults; the build driver overrides these with -D flags. */
#ifndef GR_GB_MAPPER
#define GR_GB_MAPPER 0
#endif
#ifndef GR_GB_ROM_BANKS
#define GR_GB_ROM_BANKS 2u
#endif
#ifndef GR_GB_RAM_BANKS
#define GR_GB_RAM_BANKS 0u
#endif

#ifdef __cplusplus
}
#endif

#endif /* GRAMMA_TARGET_GB_MAPPER_H */
