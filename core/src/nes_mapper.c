#include <gramma/target/nes/mapper.h>

/*
 * NES mapper register protocols.
 *
 * The generic bank-set layer owns the selected-bank cache; this file only
 * translates a slot/bank selection into the mapper's hardware register writes.
 * No NES memory-mapped I/O happens here: the backend (or a unit test) supplies
 * the low-level writer so this code also compiles on the PC test build.
 */

/* --- MMC1 --------------------------------------------------------------- */

/* Mapper register target for each serial address range. */
static uint16_t mmc1_target(uint16_t address)
{
    if (address < 0xa000u) {
        return 0xe000u;       /* control */
    }
    if (address < 0xc000u) {
        return 0xa000u;       /* PRG bank */
    }
    if (address < 0xe000u) {
        return 0xb000u;       /* CHR bank 0 */
    }
    return 0xc000u;           /* CHR bank 1 */
}

/* Address range used to clock a given MMC1 register. */
static uint16_t mmc1_serial_base(uint16_t target)
{
    if (target == 0xe000u) {
        return 0x8000u;
    }
    if (target == 0xa000u) {
        return 0xa000u;
    }
    if (target == 0xb000u) {
        return 0xc000u;
    }
    return 0xe000u;
}

static void mmc1_serial(gr_nes_mapper_state *state, uint16_t target,
                        uint8_t value)
{
    uint16_t base = mmc1_serial_base(target);
    uint8_t bit;

    /* Bit 7 resets the shift register; the following five writes clock in the
     * value LSB first. The fifth write commits it via register_write(). */
    gr_nes_mapper_register_write(state, base, 0x80u);
    for (bit = 0u; bit < 5u; ++bit) {
        gr_nes_mapper_register_write(
            state, base, (uint8_t)((value >> bit) & 1u));
    }
}

static void mmc1_prg_write(uint8_t slot, uint16_t bank, void *user)
{
    gr_nes_mapper_state *state = (gr_nes_mapper_state *)user;
    (void)slot;
    mmc1_serial(state, 0xa000u, (uint8_t)(bank & 0x0fu));
}

static void mmc1_chr_write(uint8_t slot, uint16_t bank, void *user)
{
    gr_nes_mapper_state *state = (gr_nes_mapper_state *)user;
    uint16_t target = slot == 0u ? 0xb000u : 0xc000u;
    mmc1_serial(state, target, (uint8_t)(bank & 0x1fu));
}

/* --- MMC3 --------------------------------------------------------------- */

/* R6/R7 select the two 8 KB PRG windows; R0-R3 select four 2 KB CHR windows.
 * Bit 7 of $8000 selects 4 KB CHR mode (R0/R1 for PPU $1000-$1FFF, R2-R5 for
 * PPU $0000-$0FFF); bit 6 stays clear for PRG mode 0. */
static void mmc3_reg_write(gr_nes_mapper_state *state, uint8_t reg,
                           uint8_t value)
{
    state->io_write(0x8000u, (uint8_t)(0x80u | (reg & 0x07u)), state->io_user);
    state->io_write(0x8001u, value, state->io_user);
    state->bank_select = reg;
}

static void mmc3_prg_write(uint8_t slot, uint16_t bank, void *user)
{
    gr_nes_mapper_state *state = (gr_nes_mapper_state *)user;
    mmc3_reg_write(state, (uint8_t)(6u + slot), (uint8_t)(bank & 0x3fu));
}

static void mmc3_chr_write(uint8_t slot, uint16_t bank, void *user)
{
    gr_nes_mapper_state *state = (gr_nes_mapper_state *)user;
    mmc3_reg_write(state, (uint8_t)(slot & 3u), (uint8_t)(bank & 0x7fu));
}

/* --- Runtime mapper (owned by the NES backend) ------------------------- */

static gr_nes_mapper_state g_runtime_mapper;

gr_result gr_nes_mapper_runtime_init(gr_nes_mapper id,
                                     gr_nes_io_write_fn io_write, void *io_user)
{
    return gr_nes_mapper_init_hw(&g_runtime_mapper, id, io_write, io_user);
}

gr_result gr_nes_mapper_runtime_init_layout(gr_nes_mapper id, uint8_t prg_banks,
                                             gr_nes_io_write_fn io_write,
                                             void *io_user)
{
    return gr_nes_mapper_init_hw_layout(&g_runtime_mapper, id, prg_banks,
                                        io_write, io_user);
}

gr_nes_mapper gr_nes_mapper_runtime_id(void)
{
    return g_runtime_mapper.id;
}

gr_bank_set *gr_nes_mapper_prg_banks(void)
{
    return &g_runtime_mapper.prg;
}

gr_bank_set *gr_nes_mapper_chr_banks(void)
{
    return &g_runtime_mapper.chr;
}

/* --- Shared API --------------------------------------------------------- */

gr_result gr_nes_mapper_init(gr_nes_mapper_state *state, gr_nes_mapper id)
{
    if (state == NULL) {
        return GR_ERR_INVALID_ARG;
    }
    if (id != GR_NES_MAPPER_NROM) {
        return GR_ERR_UNSUPPORTED;
    }

    state->id = id;
    state->io_write = NULL;
    state->io_user = NULL;
    state->shift = 0u;
    state->shift_count = 0u;
    state->bank_select = 0u;
    (void)gr_bank_set_init(&state->prg, 0u, NULL, NULL);
    (void)gr_bank_set_init(&state->chr, 0u, NULL, NULL);
    return GR_OK;
}

gr_result gr_nes_mapper_init_hw(gr_nes_mapper_state *state, gr_nes_mapper id,
                                gr_nes_io_write_fn io_write, void *io_user)
{
    return gr_nes_mapper_init_hw_layout(state, id, 2u, io_write, io_user);
}

/* The final two 16 KB PRG banks hold code. MMC1 exposes the switchable lower
 * window, so its active bank is N-2; MMC3 exposes two switchable 8 KB windows
 * covering that same 16 KB bank, so its registers are 2*(N-2) and 2*(N-2)+1. */
static uint16_t initial_prg_bank(gr_nes_mapper id, uint8_t prg_banks,
                                 uint8_t slot)
{
    if (prg_banks < 2u) {
        prg_banks = 2u;
    }
    if (id == GR_NES_MAPPER_MMC3) {
        return (uint16_t)(2u * (prg_banks - 2u) + slot);
    }
    return (uint16_t)(prg_banks - 2u);
}

gr_result gr_nes_mapper_init_hw_layout(gr_nes_mapper_state *state,
                                       gr_nes_mapper id, uint8_t prg_banks,
                                       gr_nes_io_write_fn io_write,
                                       void *io_user)
{
    uint8_t slot;

    if (state == NULL || (id != GR_NES_MAPPER_NROM && io_write == NULL)) {
        return GR_ERR_INVALID_ARG;
    }
    if (id == GR_NES_MAPPER_NROM) {
        return gr_nes_mapper_init(state, id);
    }
    if (id != GR_NES_MAPPER_MMC1 && id != GR_NES_MAPPER_MMC3) {
        return GR_ERR_UNSUPPORTED;
    }

    state->id = id;
    state->io_write = io_write;
    state->io_user = io_user;
    state->shift = 0u;
    state->shift_count = 0u;
    state->bank_select = 0u;

    if (id == GR_NES_MAPPER_MMC1) {
        /* Control $1E: vertical mirroring, 16 KB PRG mode, 4 KB CHR mode.
         * 4 KB CHR mode is required for $B000/$C000 to select pattern tables. */
        (void)gr_bank_set_init(&state->prg, 1u, mmc1_prg_write, state);
        (void)gr_bank_set_init(&state->chr, 2u, mmc1_chr_write, state);
        mmc1_serial(state, 0xe000u, 0x1eu);
    } else {
        /* 4 KB CHR mode (bit7 of $8000) and PRG mode 0 (bit6 clear).
         * $E000 is IRQ disable, not mode control. All CHR registers are
         * programmed so both pattern tables see the full 8 KB CHR ROM. */
        state->io_write(0xa000u, 0x00u, io_user);  /* vertical mirroring */
        state->io_write(0xe000u, 0x00u, io_user);  /* IRQ disable */
        (void)gr_bank_set_init(&state->prg, 2u, mmc3_prg_write, state);
        (void)gr_bank_set_init(&state->chr, 4u, mmc3_chr_write, state);
    }

    /* Program the default banks. MMC3's R7 must be bank 1: with PRG mode 0,
     * R6/R7 map $8000-$9FFF/$A000-$BFFF and $C000-$FFFF is fixed to the last
     * 16 KB. Setting R7 to 0 would alias the switchable PRG window to bank 0. */
    for (slot = 0u; slot < gr_bank_slots(&state->prg); ++slot) {
        (void)gr_bank_select(&state->prg, slot,
                             initial_prg_bank(id, prg_banks, slot));
    }
    for (slot = 0u; slot < gr_bank_slots(&state->chr); ++slot) {
        (void)gr_bank_select(&state->chr, slot, 0u);
    }

    if (id == GR_NES_MAPPER_MMC3) {
        /* R1 and R3 select the upper halves of the two pattern tables; R4/R5
         * are not exposed as logical slots but still need programming. */
        mmc3_reg_write(state, 1u, 1u);
        mmc3_reg_write(state, 3u, 1u);
        mmc3_reg_write(state, 4u, 2u);
        mmc3_reg_write(state, 5u, 3u);
    }
    return GR_OK;
}

void gr_nes_mapper_register_write(gr_nes_mapper_state *state,
                                  uint16_t address, uint8_t value)
{
    uint16_t target;

    if (state == NULL || state->io_write == NULL) {
        return;
    }

    if (state->id == GR_NES_MAPPER_MMC1) {
        if ((value & 0x80u) != 0u) {
            state->shift = 0u;
            state->shift_count = 0u;
            return;
        }
        state->shift |= (uint8_t)((value & 1u) << state->shift_count);
        ++state->shift_count;
        if (state->shift_count == 5u) {
            target = mmc1_target(address);
            state->io_write(target, state->shift, state->io_user);
            state->shift = 0u;
            state->shift_count = 0u;
        }
        return;
    }

    if (state->id == GR_NES_MAPPER_MMC3) {
        if (address == 0x8001u || address == 0xa001u) {
            state->io_write(0x8001u, value, state->io_user);
        } else if (address < 0xa000u) {
            state->bank_select = (uint8_t)(value & 0x07u);
        } else {
            state->io_write(address, value, state->io_user);
        }
    }
}
