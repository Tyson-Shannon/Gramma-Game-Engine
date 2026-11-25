#include <gramma/target/gb/mapper.h>

/* Game Boy MBC register protocols.
 *
 * The generic bank-set layer owns the selected-bank cache. This file only
 * validates the layout and translates a logical slot selection into a ROM or
 * SRAM bank write through the injected callback, so it compiles on the PC
 * test build without GBDK.
 */

static bool gb_mapper_supported(gr_gb_mapper id)
{
    return id == GR_GB_MAPPER_NONE || id == GR_GB_MAPPER_MBC1 ||
           id == GR_GB_MAPPER_MBC3 || id == GR_GB_MAPPER_MBC5;
}

static uint8_t gb_max_rom_banks(gr_gb_mapper id)
{
    if (id == GR_GB_MAPPER_MBC1) {
        return 32u;             /* MBC1's 5-bit register without mode switching */
    }
    return 128u;                /* MBC3/MBC5 low 8-bit register (power-of-two) */
}

static void gb_rom_write(uint8_t slot, uint16_t bank, void *user)
{
    gr_gb_mapper_state *state = (gr_gb_mapper_state *)user;
    (void)slot;
    state->write(GR_GB_BANK_ROM, bank, state->user);
}

static void gb_ram_write(uint8_t slot, uint16_t bank, void *user)
{
    gr_gb_mapper_state *state = (gr_gb_mapper_state *)user;
    (void)slot;
    state->write(GR_GB_BANK_RAM, bank, state->user);
}

gr_result gr_gb_mapper_init(gr_gb_mapper_state *state, gr_gb_mapper id,
                            uint8_t rom_banks, uint8_t ram_banks,
                            gr_gb_bank_write_fn write, void *user)
{
    if (state == NULL || !gb_mapper_supported(id)) {
        return GR_ERR_INVALID_ARG;
    }
    if (id == GR_GB_MAPPER_NONE) {
        rom_banks = 2u;
        ram_banks = 0u;
        write = NULL;
    } else {
        if (write == NULL || rom_banks < 2u ||
            rom_banks > gb_max_rom_banks(id) || ram_banks > 16u) {
            return GR_ERR_INVALID_ARG;
        }
        if ((rom_banks & (uint8_t)(rom_banks - 1u)) != 0u) {
            return GR_ERR_INVALID_ARG;
        }
        if (ram_banks != 0u &&
            (ram_banks & (uint8_t)(ram_banks - 1u)) != 0u) {
            return GR_ERR_INVALID_ARG;
        }
    }

    state->id = id;
    state->rom_banks = rom_banks;
    state->ram_banks = ram_banks;
    state->write = write;
    state->user = user;

    if (id == GR_GB_MAPPER_NONE) {
        (void)gr_bank_set_init(&state->rom, 0u, NULL, NULL);
        (void)gr_bank_set_init(&state->ram, 0u, NULL, NULL);
        return GR_OK;
    }

    /* Bank 0 remains fixed at $0000-$3FFF; the single logical slot selects
     * physical banks 1..N-1 into $4000-$7FFF. */
    (void)gr_bank_set_init(&state->rom, 1u, gb_rom_write, state);
    (void)gr_bank_set_init(&state->ram, ram_banks == 0u ? 0u : 1u,
                           gb_ram_write, state);
    (void)gr_bank_select(&state->rom, 0u, 1u);
    if (ram_banks != 0u) {
        (void)gr_bank_select(&state->ram, 0u, 0u);
    }
    return GR_OK;
}

/* --- Runtime mapper (owned by the Game Boy backend) --------------------- */

static gr_gb_mapper_state g_runtime_mapper;

gr_result gr_gb_mapper_runtime_init(gr_gb_mapper id, uint8_t rom_banks,
                                    uint8_t ram_banks,
                                    gr_gb_bank_write_fn write, void *user)
{
    return gr_gb_mapper_init(&g_runtime_mapper, id, rom_banks, ram_banks,
                             write, user);
}

gr_gb_mapper gr_gb_mapper_runtime_id(void)
{
    return g_runtime_mapper.id;
}

uint8_t gr_gb_mapper_rom_bank_count(void)
{
    return g_runtime_mapper.rom_banks;
}

uint8_t gr_gb_mapper_ram_bank_count(void)
{
    return g_runtime_mapper.ram_banks;
}

gr_bank_set *gr_gb_mapper_rom_banks(void)
{
    return &g_runtime_mapper.rom;
}

gr_bank_set *gr_gb_mapper_ram_banks(void)
{
    return &g_runtime_mapper.ram;
}
