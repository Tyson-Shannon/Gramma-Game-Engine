#include <gramma/target/sms/mapper.h>

/* Sega slot-2 mapper protocol.
 *
 * The generic bank-set layer owns the selected-bank cache. This file only
 * validates the layout and translates a logical slot selection into a mapper
 * register write through the injected callback, so it also compiles in the PC
 * unit-test build without SMSlib. */

static bool sms_power_of_two(uint8_t value)
{
    return value > 0u && (value & (uint8_t)(value - 1u)) == 0u;
}

static void sms_rom_write(uint8_t slot, uint16_t bank, void *user)
{
    gr_sms_mapper_state *state = (gr_sms_mapper_state *)user;
    (void)slot;
    state->write(bank, state->user);
}

gr_result gr_sms_mapper_init(gr_sms_mapper_state *state, uint8_t rom_banks,
                             gr_sms_bank_write_fn write, void *user)
{
    if (state == NULL || rom_banks < GR_SMS_MIN_ROM_BANKS ||
        rom_banks > GR_SMS_MAX_ROM_BANKS ||
        !sms_power_of_two(rom_banks)) {
        return GR_ERR_INVALID_ARG;
    }
    if (rom_banks > GR_SMS_MIN_ROM_BANKS && write == NULL) {
        return GR_ERR_INVALID_ARG;
    }

    state->rom_banks = rom_banks;
    state->write = write;
    state->user = user;
    if (rom_banks == GR_SMS_MIN_ROM_BANKS) {
        (void)gr_bank_set_init(&state->rom, 0u, NULL, NULL);
        return GR_OK;
    }

    /* Bank 0/1 are fixed; one slot selects banks 2..N-1 into $8000-$BFFF. */
    (void)gr_bank_set_init(&state->rom, 1u, sms_rom_write, state);
    (void)gr_bank_select(&state->rom, 0u, GR_SMS_DEFAULT_BANK);
    return GR_OK;
}

static gr_sms_mapper_state g_runtime_mapper;

gr_result gr_sms_mapper_runtime_init(uint8_t rom_banks,
                                     gr_sms_bank_write_fn write, void *user)
{
    return gr_sms_mapper_init(&g_runtime_mapper, rom_banks, write, user);
}

uint8_t gr_sms_mapper_rom_bank_count(void)
{
    return g_runtime_mapper.rom_banks;
}

gr_bank_set *gr_sms_mapper_rom_banks(void)
{
    return &g_runtime_mapper.rom;
}
