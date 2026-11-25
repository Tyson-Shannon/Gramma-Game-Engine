# Pinned toolchain containers

These Dockerfiles freeze the four console toolchains used by `gr build` so a
new contributor does not have to reproduce CLI downloads or apt state by hand.
They are **not** used by hosted CI yet; CI still installs the same versions on
the runner. No Docker builds were performed as part of the Phase 3 source
change, so a successful image build is not claimed here.

## Versions

| Tool | Version | Source | SHA-256 / pin |
| --- | --- | --- | --- |
| GBDK-2020 | 4.6.0 | release tarball | `c033dac0…7e35` |
| cc65 | 2.19 | `V2.19` source tag | `157b8051…de77` |
| SDCC | 4.5.0 | sourceforge source tarball | `d5030437…eed80` |
| devkitSMS | `561bc2cb` | commit archive | `221efd6b…5b55` |

Full checksums are `ARG`s at the top of [`Dockerfile`](Dockerfile); edit them
only when deliberately upgrading a toolchain, and update `tools/gr/gramma_cli`
plus CI in the same change.

## Build and run

```sh
./docker/build.sh                 # gbdk, cc65, sms, dev
./docker/build.sh sms             # only SDCC + devkitSMS
docker run --rm -it -v "$PWD:/workspace" gramma/dev:latest
```

Inside the combined image, `gr doctor` should report all toolchains:

```sh
./tools/gr/gr doctor
./tools/gr/gr build --target pc
./tools/gr/gr build --target gb
./tools/gr/gr build --target nes
./tools/gr/gr build --target sms
```

The environment variables line up with the CLI's discovery rules, so no
download into `~/.cache/gramma` is attempted:

- `GBDK_HOME=/opt/gbdk`
- `CC65_HOME=/opt/cc65`
- `SDCC_HOME=/opt/sdcc`
- `DEVKITSMS_HOME=/opt/devkitsms`

Individual stages export only their own variable and toolchain. For example,
`docker run --rm -v "$PWD:/workspace" gramma/gbdk:4.6.0 ./tools/gr/gr build
--target gb` builds a Game Boy ROM without installing the other compilers.

## Notes

- The base is `ubuntu:24.04` and is pinned by the `UBUNTU_VERSION` build arg.
- `cc65` and `SDCC` are compiled from source because Debian package versions
  change with the Ubuntu release; compiling from a pinned tag makes the image
  independent of apt package churn.
- The `sms` stage installs the devkitSMS archive at the exact commit used by
  the CLI and CI, including its prebuilt `SMSlib.lib` and `makesms`.
- The `dev` stage adds host dependencies, Python 3.13-compatible emulator
  packages, Meson/Ninja and Node for the VS Code adapter test.
