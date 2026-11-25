gramma_inc = include_directories('include')

core_sources = files(
    'src/math.c',
    'src/actor.c',
    'src/scene.c',
    'src/api.c',
    'src/bank.c',
    'src/nes_mapper.c',
    'src/gb_mapper.c',
    'src/sms_mapper.c',
    'src/overlay.c',
)

gramma_core = static_library('gramma_core', core_sources,
    include_directories: gramma_inc,
    c_args: ['-DGRAMMA_TARGET_' + target.to_upper()])

gramma_dep = declare_dependency(
    link_with: gramma_core,
    include_directories: gramma_inc,
)
