pc_inc = include_directories('include')

gramma_pc = static_library('gramma_pc',
    files(
        'src/pc_backend.c',
        'src/render_soft.c',
        'src/audio.c',
    ),
    include_directories: [gramma_inc, pc_inc],
    dependencies: sdl_dep,
    c_args: ['-DGRAMMA_TARGET_PC'])

gramma_pc_dep = declare_dependency(
    link_with: gramma_pc,
    dependencies: sdl_dep,
    include_directories: [gramma_inc, pc_inc])
