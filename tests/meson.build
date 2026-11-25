math_test = executable('test_math', files('test_math.c'),
    dependencies: [gramma_dep])
test('fixed-point math', math_test)

bank_test = executable('test_bank', files('test_bank.c'),
    dependencies: [gramma_dep])
test('bank abstraction', bank_test)

gb_mapper_test = executable('test_gb_mapper', files('test_gb_mapper.c'),
    dependencies: [gramma_dep])
test('Game Boy mapper', gb_mapper_test)

sms_mapper_test = executable('test_sms_mapper', files('test_sms_mapper.c'),
    dependencies: [gramma_dep])
test('SMS mapper', sms_mapper_test)

overlay_deps = [gramma_dep]
if target == 'pc'
    overlay_deps += gramma_pc_dep
endif
overlay_test = executable('test_overlay', files('test_overlay.c'),
    dependencies: overlay_deps)
test('vblank overlay queue', overlay_test)

target_system_test = executable('test_target_system',
    files('test_target_system.c'), dependencies: [gramma_dep])
test('target system extensions', target_system_test)

nes_depth_test = executable('test_nes_depth', files('test_nes_depth.c'),
    dependencies: [gramma_dep])
test('NES depth helpers', nes_depth_test)
