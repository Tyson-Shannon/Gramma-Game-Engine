subdir('generated/' + target)

# Grain emits the complete game (actors, scene, config and main) as C, so there
# are no hand-written sources here.
game = executable('game',
    generated_sources,
    dependencies: [gramma_dep, gramma_pc_dep],
)
