#include <gramma/bank.h>
#include <gramma/target/nes/mapper.h>
#include <assert.h>
#include <string.h>

#define MAX_IO_WRITES 64u

static uint16_t g_last_bank;
static uint8_t g_last_slot;
static unsigned g_writes;

static void fake_bank_write(uint8_t slot, uint16_t bank, void *user)
{
    ++g_writes;
    g_last_slot = slot;
    g_last_bank = bank;
    *((unsigned *)user) = g_writes;
}

typedef struct {
    uint16_t address[MAX_IO_WRITES];
    uint8_t  value[MAX_IO_WRITES];
    uint8_t  count;
} io_log;

static void fake_io_write(uint16_t address, uint8_t value, void *user)
{
    io_log *log = (io_log *)user;
    if (log->count < MAX_IO_WRITES) {
        log->address[log->count] = address;
        log->value[log->count] = value;
        ++log->count;
    }
}

/* True when the log contains a write to `address` with `value`. */
static bool io_has(const io_log *log, uint16_t address, uint8_t value)
{
    uint8_t i;
    for (i = 0u; i < log->count; ++i) {
        if (log->address[i] == address && log->value[i] == value) {
            return true;
        }
    }
    return false;
}

static void test_generic_bank_set(void)
{
    gr_bank_set set;

    assert(gr_bank_set_init(&set, 2u, fake_bank_write, &g_writes) == GR_OK);
    assert(gr_bank_slots(&set) == 2u);
    assert(gr_bank_current(&set, 0u) == 0u);

    assert(gr_bank_select(&set, 1u, 7u) == GR_OK);
    assert(gr_bank_current(&set, 1u) == 7u);
    assert(g_writes == 1u);
    assert(g_last_slot == 1u);
    assert(g_last_bank == 7u);

    assert(gr_bank_select(&set, 2u, 3u) == GR_ERR_INVALID_ARG);
    assert(gr_bank_current(&set, 2u) == 0u);
    assert(g_writes == 1u);

    assert(gr_bank_set_init(&set, GR_BANK_MAX_SLOTS + 1u, NULL, NULL) ==
           GR_ERR_INVALID_ARG);
    assert(gr_bank_set_init(&set, 0u, NULL, NULL) == GR_OK);
    assert(gr_bank_slots(&set) == 0u);
    assert(gr_bank_select(&set, 0u, 1u) == GR_ERR_INVALID_ARG);
}

static void test_bank_switch_helper(void)
{
    gr_bank_set set;
    gr_bank_switch sw;

    assert(gr_bank_set_init(&set, 1u, fake_bank_write, &g_writes) == GR_OK);
    assert(gr_bank_switch_init(&sw, &set, 0u, 10u, 20u) == GR_OK);
    assert(gr_bank_current(&set, 0u) == 10u);
    assert(gr_bank_switch_toggle(&sw) == 20u);
    assert(gr_bank_current(&set, 0u) == 20u);
    assert(gr_bank_switch_toggle(&sw) == 10u);
    assert(gr_bank_switch_reset(&sw) == GR_OK);
    assert(gr_bank_current(&set, 0u) == 10u);
    assert(gr_bank_switch_init(&sw, NULL, 0u, 1u, 2u) == GR_ERR_INVALID_ARG);
}

static void test_nrom(void)
{
    gr_nes_mapper_state mapper;

    assert(gr_nes_mapper_init(&mapper, GR_NES_MAPPER_NROM) == GR_OK);
    assert(mapper.id == GR_NES_MAPPER_NROM);
    assert(gr_bank_slots(&mapper.prg) == 0u);
    assert(gr_bank_slots(&mapper.chr) == 0u);
    assert(gr_nes_mapper_init(&mapper, GR_NES_MAPPER_MMC1) ==
           GR_ERR_UNSUPPORTED);
    assert(gr_nes_mapper_init(&mapper, GR_NES_MAPPER_MMC3) ==
           GR_ERR_UNSUPPORTED);
    assert(gr_nes_mapper_init(NULL, GR_NES_MAPPER_NROM) ==
           GR_ERR_INVALID_ARG);
    assert(gr_nes_mapper_init_hw(&mapper, GR_NES_MAPPER_MMC1, NULL, NULL) ==
           GR_ERR_INVALID_ARG);
}

static void test_mmc1(void)
{
    gr_nes_mapper_state mapper;
    io_log log;

    memset(&log, 0, sizeof(log));
    assert(gr_nes_mapper_init_hw(&mapper, GR_NES_MAPPER_MMC1,
                                 fake_io_write, &log) == GR_OK);
    assert(gr_bank_slots(&mapper.prg) == 1u);
    assert(gr_bank_slots(&mapper.chr) == 2u);
    /* Init programs control 0x1E (4 KB CHR mode) and bank 0 in all windows. */
    assert(io_has(&log, 0xe000u, 0x1eu));
    assert(io_has(&log, 0xa000u, 0x00u));
    assert(io_has(&log, 0xb000u, 0x00u));
    assert(io_has(&log, 0xc000u, 0x00u));

    memset(&log, 0, sizeof(log));
    assert(gr_bank_select(&mapper.prg, 0u, 5u) == GR_OK);
    assert(gr_bank_current(&mapper.prg, 0u) == 5u);
    /* Five serial bit clocks collapse to one hardware register commit. */
    assert(log.count == 1u);
    assert(log.address[0] == 0xa000u && log.value[0] == 5u);

    memset(&log, 0, sizeof(log));
    assert(gr_bank_select(&mapper.chr, 1u, 3u) == GR_OK);
    assert(log.count == 1u);
    assert(log.address[0] == 0xc000u && log.value[0] == 3u);
}

static void test_mmc3(void)
{
    gr_nes_mapper_state mapper;
    io_log log;

    memset(&log, 0, sizeof(log));
    assert(gr_nes_mapper_init_hw(&mapper, GR_NES_MAPPER_MMC3,
                                 fake_io_write, &log) == GR_OK);
    assert(gr_bank_slots(&mapper.prg) == 2u);
    assert(gr_bank_slots(&mapper.chr) == 4u);
    assert(io_has(&log, 0xa000u, 0x00u));   /* vertical mirroring */
    assert(io_has(&log, 0xe000u, 0x00u));   /* IRQ disable */
    /* Every $8000 write keeps bit7 set for 4 KB CHR mode. */
    assert(io_has(&log, 0x8000u, 0x86u));   /* R6 */
    assert(io_has(&log, 0x8000u, 0x87u));   /* R7 */
    assert(io_has(&log, 0x8000u, 0x80u));   /* R0 */
    assert(io_has(&log, 0x8000u, 0x85u));   /* R5 */
    /* R7 defaults to bank 1 so $A000-$BFFF keeps the second PRG window. */
    assert(gr_bank_current(&mapper.prg, 0u) == 0u);
    assert(gr_bank_current(&mapper.prg, 1u) == 1u);

    memset(&log, 0, sizeof(log));
    assert(gr_bank_select(&mapper.prg, 1u, 9u) == GR_OK);
    assert(gr_bank_current(&mapper.prg, 1u) == 9u);
    assert(log.count == 2u);
    assert(log.address[0] == 0x8000u && log.value[0] == 0x87u); /* R7 */
    assert(log.address[1] == 0x8001u && log.value[1] == 9u);

    memset(&log, 0, sizeof(log));
    assert(gr_bank_select(&mapper.chr, 2u, 11u) == GR_OK);
    assert(log.count == 2u);
    assert(log.address[0] == 0x8000u && log.value[0] == 0x82u); /* R2 */
    assert(log.address[1] == 0x8001u && log.value[1] == 11u);
}

static void test_larger_prg_layout(void)
{
    gr_nes_mapper_state mapper;
    io_log log;

    memset(&log, 0, sizeof(log));
    assert(gr_nes_mapper_init_hw_layout(&mapper, GR_NES_MAPPER_MMC3, 4u,
                                        fake_io_write, &log) == GR_OK);
    /* With four 16 KB banks, code lives in banks 2 and 3: R6/R7 are 4/5. */
    assert(gr_bank_current(&mapper.prg, 0u) == 4u);
    assert(gr_bank_current(&mapper.prg, 1u) == 5u);
    assert(io_has(&log, 0x8001u, 4u));
    assert(io_has(&log, 0x8001u, 5u));

    memset(&log, 0, sizeof(log));
    assert(gr_nes_mapper_init_hw_layout(&mapper, GR_NES_MAPPER_MMC1, 4u,
                                        fake_io_write, &log) == GR_OK);
    /* MMC1's switchable lower window must show bank 2. */
    assert(gr_bank_current(&mapper.prg, 0u) == 2u);
    assert(io_has(&log, 0xa000u, 2u));
}

static void test_runtime_mapper(void)
{
    io_log log;

    memset(&log, 0, sizeof(log));
    assert(gr_nes_mapper_runtime_init(GR_NES_MAPPER_MMC3,
                                      fake_io_write, &log) == GR_OK);
    assert(gr_nes_mapper_runtime_id() == GR_NES_MAPPER_MMC3);
    assert(gr_bank_slots(gr_nes_mapper_prg_banks()) == 2u);
    assert(gr_bank_slots(gr_nes_mapper_chr_banks()) == 4u);

    memset(&log, 0, sizeof(log));
    assert(gr_bank_select(gr_nes_mapper_chr_banks(), 0u, 3u) == GR_OK);
    assert(gr_bank_current(gr_nes_mapper_chr_banks(), 0u) == 3u);
    assert(log.count == 2u);
    assert(log.address[0] == 0x8000u && log.value[0] == 0x80u);
    assert(log.address[1] == 0x8001u && log.value[1] == 3u);

    /* Reset to NROM so later tests see a clean runtime state. */
    assert(gr_nes_mapper_runtime_init(GR_NES_MAPPER_NROM, NULL, NULL) == GR_OK);
    assert(gr_nes_mapper_runtime_id() == GR_NES_MAPPER_NROM);
    assert(gr_bank_slots(gr_nes_mapper_prg_banks()) == 0u);
}

int main(void)
{
    test_generic_bank_set();
    test_bank_switch_helper();
    test_nrom();
    test_mmc1();
    test_mmc3();
    test_larger_prg_layout();
    test_runtime_mapper();
    return 0;
}
