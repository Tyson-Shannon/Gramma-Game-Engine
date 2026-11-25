#include <gramma/target/sms/mapper.h>
#include <assert.h>
#include <string.h>

typedef struct {
    uint16_t bank[16];
    uint8_t  count;
} sms_log;

static void fake_sms_write(uint16_t bank, void *user)
{
    sms_log *log = (sms_log *)user;
    if (log->count < 16u) {
        log->bank[log->count] = bank;
        ++log->count;
    }
}

static bool sms_log_has(const sms_log *log, uint16_t bank)
{
    uint8_t i;
    for (i = 0u; i < log->count; ++i) {
        if (log->bank[i] == bank) {
            return true;
        }
    }
    return false;
}

static void test_plain_rom(void)
{
    gr_sms_mapper_state mapper;

    assert(gr_sms_mapper_init(&mapper, 2u, NULL, NULL) == GR_OK);
    assert(mapper.rom_banks == 2u);
    assert(gr_bank_slots(&mapper.rom) == 0u);
    assert(gr_bank_select(&mapper.rom, 0u, 2u) == GR_ERR_INVALID_ARG);
}

static void test_slot2(void)
{
    gr_sms_mapper_state mapper;
    sms_log log;

    memset(&log, 0, sizeof(log));
    assert(gr_sms_mapper_init(&mapper, 4u, fake_sms_write, &log) == GR_OK);
    assert(gr_bank_slots(&mapper.rom) == 1u);
    assert(sms_log_has(&log, GR_SMS_DEFAULT_BANK));

    log.count = 0u;
    assert(gr_bank_select(&mapper.rom, 0u, 3u) == GR_OK);
    assert(gr_bank_current(&mapper.rom, 0u) == 3u);
    assert(log.count == 1u && log.bank[0] == 3u);
}

static void test_validation(void)
{
    gr_sms_mapper_state mapper;
    sms_log log;

    memset(&log, 0, sizeof(log));
    assert(gr_sms_mapper_init(&mapper, 3u, fake_sms_write, &log) ==
           GR_ERR_INVALID_ARG);
    assert(gr_sms_mapper_init(&mapper, 1u, fake_sms_write, &log) ==
           GR_ERR_INVALID_ARG);
    assert(gr_sms_mapper_init(&mapper, 128u, fake_sms_write, &log) ==
           GR_ERR_INVALID_ARG);
    assert(gr_sms_mapper_init(&mapper, 4u, NULL, NULL) ==
           GR_ERR_INVALID_ARG);
    assert(gr_sms_mapper_init(NULL, 4u, fake_sms_write, &log) ==
           GR_ERR_INVALID_ARG);
}

static void test_runtime_mapper(void)
{
    sms_log log;

    memset(&log, 0, sizeof(log));
    assert(gr_sms_mapper_runtime_init(4u, fake_sms_write, &log) == GR_OK);
    assert(gr_sms_mapper_rom_bank_count() == 4u);
    assert(gr_bank_slots(gr_sms_mapper_rom_banks()) == 1u);
    assert(gr_bank_select(gr_sms_mapper_rom_banks(), 0u, 2u) == GR_OK);
    assert(sms_log_has(&log, 2u));

    assert(gr_sms_mapper_runtime_init(2u, NULL, NULL) == GR_OK);
    assert(gr_sms_mapper_rom_bank_count() == 2u);
    assert(gr_bank_slots(gr_sms_mapper_rom_banks()) == 0u);
}

int main(void)
{
    test_plain_rom();
    test_slot2();
    test_validation();
    test_runtime_mapper();
    return 0;
}
