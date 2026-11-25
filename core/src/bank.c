#include <gramma/bank.h>

/* A logical bank set tracks the selected bank for each slot and delegates the
 * hardware write to the backend when one is provided. Keeping the cache here
 * means backends only implement their mapper's register writes. */

static bool gr_bank_valid_slot(const gr_bank_set *set, uint8_t slot)
{
    return set != NULL && slot < set->slot_count;
}

gr_result gr_bank_set_init(gr_bank_set *set, uint8_t slot_count,
                           gr_bank_write_fn write, void *user)
{
    uint8_t i;

    if (set == NULL || slot_count > GR_BANK_MAX_SLOTS) {
        return GR_ERR_INVALID_ARG;
    }
    set->slot_count = slot_count;
    for (i = 0; i < GR_BANK_MAX_SLOTS; ++i) {
        set->current[i] = 0u;
    }
    set->write = write;
    set->user = user;
    return GR_OK;
}

gr_result gr_bank_select(gr_bank_set *set, uint8_t slot, uint16_t bank)
{
    if (!gr_bank_valid_slot(set, slot)) {
        return GR_ERR_INVALID_ARG;
    }
    set->current[slot] = bank;
    if (set->write != NULL) {
        set->write(slot, bank, set->user);
    }
    return GR_OK;
}

uint8_t gr_bank_slots(const gr_bank_set *set)
{
    return set == NULL ? 0u : set->slot_count;
}

uint16_t gr_bank_current(const gr_bank_set *set, uint8_t slot)
{
    if (!gr_bank_valid_slot(set, slot)) {
        return 0u;
    }
    return set->current[slot];
}

gr_result gr_bank_switch_init(gr_bank_switch *sw, gr_bank_set *set,
                              uint8_t slot, uint16_t bank_a, uint16_t bank_b)
{
    if (sw == NULL || !gr_bank_valid_slot(set, slot)) {
        return GR_ERR_INVALID_ARG;
    }
    sw->set = set;
    sw->slot = slot;
    sw->bank_a = bank_a;
    sw->bank_b = bank_b;
    sw->alternate = false;
    return gr_bank_select(set, slot, bank_a);
}

uint16_t gr_bank_switch_toggle(gr_bank_switch *sw)
{
    uint16_t bank;

    if (sw == NULL) {
        return 0u;
    }
    bank = sw->alternate ? sw->bank_a : sw->bank_b;
    if (gr_bank_select(sw->set, sw->slot, bank) != GR_OK) {
        return 0u;
    }
    sw->alternate = !sw->alternate;
    return bank;
}

gr_result gr_bank_switch_reset(gr_bank_switch *sw)
{
    if (sw == NULL) {
        return GR_ERR_INVALID_ARG;
    }
    sw->alternate = false;
    return gr_bank_select(sw->set, sw->slot, sw->bank_a);
}
