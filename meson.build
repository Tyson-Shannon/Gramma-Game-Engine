project('gramma', 'c',
    version: '0.1.0',
    default_options: ['c_std=c99', 'warning_level=2'])

target = get_option('target')

add_project_arguments('-DGRAMMA_TARGET_' + target.to_upper(), language: 'c')

subdir('core')

if target == 'pc'
    sdl_dep = dependency('sdl2', required: false)
    if not sdl_dep.found()
        sdl_inc_dirs = []
        sdl_include = get_option('sdl_include')
        sdl_arch_include = get_option('sdl_arch_include')
        sdl_link = get_option('sdl_library')
        if sdl_include != ''
            sdl_inc_dirs += include_directories(sdl_include)
        endif
        if sdl_arch_include != '' and sdl_arch_include != sdl_include
            sdl_inc_dirs += include_directories(sdl_arch_include)
        endif
        if sdl_link == ''
            error('SDL2 development files not found. Install libsdl2-dev or run `gr doctor`.')
        endif
        sdl_link_args = [sdl_link]
        sdl_dep = declare_dependency(
            include_directories: sdl_inc_dirs,
            link_args: sdl_link_args)
    endif
    subdir('targets/pc')
endif

subdir(get_option('project'))
subdir('tests')
