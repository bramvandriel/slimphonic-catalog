# Slimphonic plugin catalogue

The curated list of free, open-source audio plugins that the
[Slimphonic](https://github.com/bramvandriel/slimphonic) DAW's Browser offers
to install, one manifest per platform:

- `linux.json` — Linux x86_64 (CLAP preferred; VST3 only where no CLAP exists)
- `windows.json`, `macos.json` — later

Each entry names the upstream project, its licence, a pinned release asset
(URL, size and SHA-256 checksum), the plugin files inside that archive, and a
short description. Slimphonic ships a copy of this file inside the binary;
this repository is where it is maintained and, later, where the app refreshes
it from (signed with minisign).

The seed for most entries is the
[Open Audio Stack registry](https://github.com/open-audio-stack/open-audio-stack-registry)
(CC0), with Slimphonic's own editorial overlay (editor's picks, warnings,
link-only entries) on top. Corrections to facts that come from that registry
are contributed back upstream.

## Contributing

An entry is accepted when the plugin is open source, has a Linux release asset
on GitHub, and loads in Slimphonic. Open an issue or a pull request against the
JSON; the app's own validation rules (https-only URLs, GitHub-hosted assets,
relative plugin paths, bounded sizes) apply.

## Licence

The catalogue data is dedicated to the public domain under CC0 1.0
(see `LICENSE`). The plugins it points to keep their own licences, named in
each entry.
