#ifndef GRAMMA_TARGET_NES_MAPPER_H
#define GRAMMA_TARGET_NES_MAPPER_H

/*
 * Opt-in NES mapper extension. NROM is the default; MMC1 and MMC3 expose real
 * switchable bank sets whose writes are translated into mapper register
 * sequences. See docs/banking.md.
 */

#include <gramma/bank.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    GR_NES_MAPPER_NROM = 0,
    GR_NES_MAPPER_MMC1 = 1,
    GR_NES_MAPPER_MMC3 = 4
} gr_nes_mapper;

/* Low-level 8-bit register access. The backend supplies volatile hardware
 * stores; unit tests supply a recorder. */
typedef void (*gr_nes_io_write_fn)(uint16_t address, uint8_t value, void *user);

typedef struct {
    gr_nes_mapper     id;
    gr_bank_set       prg;
    gr_bank_set       chr;
    gr_nes_io_write_fn io_write;
    void             *io_user;
    uint8_t           shift;        /* MMC1 5-bit serial shift register */
    uint8_t           shift_count;  /* bits accumulated so far (0..5) */
    uint8_t           bank_select;  /* MMC3 $8000 latch */
} gr_nes_mapper_state;

/* Initialise a mapper with no hardware writer. Only NROM is supported here;
 * MMC1/MMC3 IDs return GR_ERR_UNSUPPORTED so callers cannot silently create a
 * banked mapper without a register writer. */
gr_result gr_nes_mapper_init(gr_nes_mapper_state *state, gr_nes_mapper id);

/* Initialise a mapper with hardware register access. MMC1 installs one 16 KB
 * PRG slot and two 4 KB CHR slots; MMC3 installs two 8 KB PRG slots and four
 * 2 KB CHR slots. Both program their default control register and bank 0. */
gr_result gr_nes_mapper_init_hw(gr_nes_mapper_state *state, gr_nes_mapper id,
                                gr_nes_io_write_fn io_write, void *io_user);

/* Apply one raw register write. MMC1 accumulates five serial bits before
 * updating a register; MMC3 latches $8000/$8001 writes. Exposed so backends
 * and tests can drive the same code path used by the bank writers. */
void gr_nes_mapper_register_write(gr_nes_mapper_state *state,
                                  uint16_t address, uint8_t value);

/* Runtime mapper owned by the NES backend. `gr_init()` initialises it from
 * the build-time `[mapper.nes]` configuration with a real hardware writer;
 * games should not call the init function themselves. */
gr_result gr_nes_mapper_runtime_init(gr_nes_mapper id,
                                     gr_nes_io_write_fn io_write, void *io_user);

/* Hardware init with an explicit 16 KB PRG bank count. Larger layouts keep
 * code in the final two banks and expose earlier banks as data; MMC1/MMC3
 * startup registers must select those final banks. */
gr_result gr_nes_mapper_init_hw_layout(gr_nes_mapper_state *state,
                                       gr_nes_mapper id, uint8_t prg_banks,
                                       gr_nes_io_write_fn io_write,
                                       void *io_user);

gr_result gr_nes_mapper_runtime_init_layout(gr_nes_mapper id, uint8_t prg_banks,
                                             gr_nes_io_write_fn io_write,
                                             void *io_user);
gr_nes_mapper gr_nes_mapper_runtime_id(void);
gr_bank_set *gr_nes_mapper_prg_banks(void);
gr_bank_set *gr_nes_mapper_chr_banks(void);

/* Copy bytes out of a data-only PRG bank into RAM. This helper runs from RAM
 * on NES so it can switch R6/MMC1's window without swapping out its caller.
 * `prg_bank` is a 16 KB file bank; `offset` is local to that bank. */
gr_result gr_nes_prg_read(uint8_t prg_bank, uint16_t offset,
                          uint8_t *dst, uint16_t length);

/* Assets are placed in 8 KB CHR banks, while MMC1/MMC3 bank registers select
 * 4 KB tables in the mode Gramma programs. Each 8 KB bank mirrors its first
 * 4 KB table into the second, so either half selects the same tiles. */
#define GR_NES_CHR_BANK4(bank_8k) ((uint16_t)((bank_8k) * 2u))

#ifdef __cplusplus
}
#endif

#endif /* GRAMMA_TARGET_NES_MAPPER_H */
