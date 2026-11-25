#include <gramma/target/gb/mapper.h>
#include <assert.h>
#include <string.h>

typedef struct {
    uint8_t  kind[16];
    uint16_t bank[16];
    uint8_t  count;
} gb_log;

static void fake_gb_write(uint8_t kind, uint16_t bank, void *user)
{
    gb_log *log = (gb_log *)user;
    if (log->count < 16u) {
        log->kind[log->count] = kind;
        log->bank[log->count] = bank;
        ++log->count;
    }
}

static bool gb_log_has(const gb_log *log, uint8_t kind, uint16_t bank)
{
    uint8_t i;
    for (i = 0u; i < log->count; ++i) {
        if (log->kind[i] == kind && log->bank[i] == bank) {
            return true;
        }
    }
    return false;
}

static void test_plain_rom(void)
{
    gr_gb_mapper_state mapper;

    assert(gr_gb_mapper_init(&mapper, GR_GB_MAPPER_NONE, 2u, 0u,
                             NULL, NULL) == GR_OK);
    assert(mapper.id == GR_GB_MAPPER_NONE);
    assert(mapper.rom_banks == 2u);
    assert(gr_bank_slots(&mapper.rom) == 0u);
    assert(gr_bank_slots(&mapper.ram) == 0u);
    assert(gr_bank_select(&mapper.rom, 0u, 1u) == GR_ERR_INVALID_ARG);
}

static void test_mbc1(void)
{
    gr_gb_mapper_state mapper;
    gb_log log;

    memset(&log, 0, sizeof(log));
    assert(gr_gb_mapper_init(&mapper, GR_GB_MAPPER_MBC1, 4u, 2u,
                             fake_gb_write, &log) == GR_OK);
    assert(gr_bank_slots(&mapper.rom) == 1u);
    assert(gr_bank_slots(&mapper.ram) == 1u);
    assert(gb_log_has(&log, GR_GB_BANK_ROM, 1u));
    assert(gb_log_has(&log, GR_GB_BANK_RAM, 0u));

    log.count = 0u;
    assert(gr_bank_select(&mapper.rom, 0u, 3u) == GR_OK);
    assert(gr_bank_current(&mapper.rom, 0u) == 3u);
    assert(log.count == 1u);
    assert(log.kind[0] == GR_GB_BANK_ROM && log.bank[0] == 3u);

    log.count = 0u;
    assert(gr_bank_select(&mapper.ram, 0u, 1u) == GR_OK);
    assert(gr_bank_current(&mapper.ram, 0u) == 1u);
    assert(log.count == 1u);
    assert(log.kind[0] == GR_GB_BANK_RAM && log.bank[0] == 1u);
}

static void test_validation(void)
{
    gr_gb_mapper_state mapper;
    gb_log log;

    memset(&log, 0, sizeof(log));
    assert(gr_gb_mapper_init(&mapper, GR_GB_MAPPER_MBC1, 3u, 0u,
                             fake_gb_write, &log) == GR_ERR_INVALID_ARG);
    assert(gr_gb_mapper_init(&mapper, GR_GB_MAPPER_MBC1, 64u, 0u,
                             fake_gb_write, &log) == GR_ERR_INVALID_ARG);
    assert(gr_gb_mapper_init(&mapper, GR_GB_MAPPER_MBC3, 4u, 3u,
                             fake_gb_write, &log) == GR_ERR_INVALID_ARG);
    assert(gr_gb_mapper_init(&mapper, GR_GB_MAPPER_MBC5, 4u, 0u,
                             NULL, NULL) == GR_ERR_INVALID_ARG);
    assert(gr_gb_mapper_init(&mapper, (gr_gb_mapper)7, 4u, 0u,
                             fake_gb_write, &log) == GR_ERR_INVALID_ARG);
    assert(gr_gb_mapper_init(NULL, GR_GB_MAPPER_MBC1, 4u, 0u,
                             fake_gb_write, &log) == GR_ERR_INVALID_ARG);
}

static void test_runtime_mapper(void)
{
    gb_log log;

    memset(&log, 0, sizeof(log));
    assert(gr_gb_mapper_runtime_init(GR_GB_MAPPER_MBC1, 4u, 0u,
                                     fake_gb_write, &log) == GR_OK);
    assert(gr_gb_mapper_runtime_id() == GR_GB_MAPPER_MBC1);
    assert(gr_gb_mapper_rom_bank_count() == 4u);
    assert(gr_gb_mapper_ram_bank_count() == 0u);
    assert(gr_bank_slots(gr_gb_mapper_rom_banks()) == 1u);
    assert(gr_bank_slots(gr_gb_mapper_ram_banks()) == 0u);
    assert(gr_bank_select(gr_gb_mapper_rom_banks(), 0u, 2u) == GR_OK);
    assert(gb_log_has(&log, GR_GB_BANK_ROM, 2u));

    assert(gr_gb_mapper_runtime_init(GR_GB_MAPPER_NONE, 2u, 0u,
                                     NULL, NULL) == GR_OK);
    assert(gr_gb_mapper_runtime_id() == GR_GB_MAPPER_NONE);
    assert(gr_gb_mapper_rom_bank_count() == 2u);
    assert(gr_bank_slots(gr_gb_mapper_rom_banks()) == 0u);
}

int main(void)
{
    test_plain_rom();
    test_mbc1();
    test_validation();
    test_runtime_mapper();
    return 0;
}
