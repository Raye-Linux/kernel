# Raye kernel

Ubuntu's kernel, same version and configuration, with a few changes for
desktops and laptops and the Raye crash screen: when the kernel panics, the
screen turns night violet and shows the Raye eye and a short message, in
English and French, saying that Raye has to restart and that your files
are safe.

- `patches/` the Raye patches
- `config/` configuration fragments
- `xanmod/` and `xanmod_lts.py` the desktop patch series Raye follows
- `art/` the crash screen picture
- `docs/` what was measured, and why each change is in

## Build

As root, in an Ubuntu resolute system with deb-src enabled:

    KEYS=/path/to/keys ./build.sh 7.0.0-43.43

`KEYS` is the folder with the signing keys; they are never in this
repository.

## Test

    python3 -m pytest art/
    ./fetch-sources.sh 7.0.0-42.42     # a few small files from the kernel source
    python3 -m pytest tests/

## License

GPL-2.0, like Linux (`LICENSE`).

## Links

- Website: https://rayelinux.com
- Discord: https://discord.gg/TrxhUkabyB (questions, bug reports, news)
