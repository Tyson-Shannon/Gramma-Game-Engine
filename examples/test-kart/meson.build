subdir('generated/' + target)

game = executable('game',
    [files('src/main.c', 'src/chr_switch.c'), generated_sources],
    dependencies: [gramma_dep, gramma_pc_dep],
)
