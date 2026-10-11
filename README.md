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

## Regenerating linux.json

`linux.json` is generated; edit `overlay/<catalog_id>.json`, not the manifest.

```
python3 -I tools/catalog_refresh.py --oas oas/index.json --overlay overlay/ --hidden hidden.json \
    --categories categories.json --out linux.json
python3 -I -m unittest discover -s tools
git diff linux.json
```

The script is standard-library Python and never touches the network. `oas/index.json` is a
dated copy of the Open Audio Stack index (`oas/SNAPSHOT.md`); refresh it by hand. Add
`--date YYYY-MM-DD` for a reproducible `generated_at`. The script prints `note:` lines where
OAS no longer lists a pinned asset or its checksum differs (expected for rolling tags), and
ends by validating the result with the same rules as the app's `manifest::validate`.
`tools/split_overlay.py` is the one-off that created the overlay from the hand-written file.

An overlay file holds what OAS cannot provide, and wins over OAS wherever it sets a field:

- always: `catalog_id`, `order` (list position), `oas_id` (OAS package key, or null),
  `editors_pick`, `score_note`, `tested_with`, `description`, `experimental`, `rolling_tag`,
  `github` (the stars/release snapshot), `formats` (plugin ids, class ids, archive globs),
  `content`, `install` (per platform: the pinned url, version, sha256, size, archive kind,
  paths' companions, link-only fields)
- only where OAS's value is wrong or missing: `name`, `vendor`, `kind`, `homepage`,
  `source`, `image`, `license` (`spdx`, `url`)

`tools/check_globs.py --overlay overlay/ --archives DIR...` lists each pinned archive found in
the given directories (tar, unzip, 7z, ar; nothing is extracted) and checks that every plugin
glob and companion matches a member and that size and sha256 equal the pin.
`upstream/open-audio-stack.md` lists the corrections to send to the Open Audio Stack registry.

## The Editor-hidden list

`hidden.json` (repository root) is the list of plugins the app puts under the Browser's
**Hidden** header for everyone, "hidden by the Editor": `[{"key": "ladspa:2601", "name":
"C* CabinetIII"}, ...]`. `key` is the app's plugin key: `clap:<plugin id>`, `vst3:<32
lowercase hex class id>` or `ladspa:<UniqueID>`; `name` is for the human reading this file.
The script copies it into `linux.json` as the top-level `hidden` list (it is not an overlay:
one overlay per catalogue entry). A user can still unhide any of them. To change the list,
edit `hidden.json`, regenerate, run the tests and copy `linux.json` into the app's
`catalog/`.

## Instrument categories

The app's Instruments tab groups plugins by their primary sound source. The manifest's
top-level `categories` list (`[{"key", "name", "category"}]`, sorted by key) is generated from
two sources:

- each overlay's `formats.clap.categories` map, `{"<clap plugin id>": "<category>"}`, next to
  the ids it describes; for a VST3-only entry `formats.vst3.categories`, keyed by class id. A
  dual-format entry is categorised under its CLAP ids only (the app finds the VST3 face through
  its alias). The maps are not copied into the entries of `linux.json`.
- `categories.json` (repository root, hand-edited, sorted by key) for plugins outside the
  catalogue: the bundled Slim instruments and known system packages.

Categories, in Browser order: `subtractive` (Subtractive and Virtual Analog), `wavetable`,
`fm`, `additive` (Additive and spectral), `physical` (Physical modelling), `keys` (Keys and
organs), `sampler`, `drums`, `modular` (Modular, plugin hosts included), `other`. They are
mutually exclusive; the first rule that fits wins:

1. dedicated to one instrument family (a drum synth, a piano, an organ): `drums` or `keys`,
   whatever the engine;
2. recordings are the main sound source: `sampler`;
3. a patchable environment or a plugin host: `modular`;
4. otherwise a synth by its primary synthesis method (`subtractive`, `wavetable`, `fm`,
   `additive`, `physical`); `other` when no single method dominates;
5. not an instrument, or nothing known: `other`.

The script refuses to write a manifest when a category is unknown, a key has two rows, a map key
is not one of its format's ids, or an instrument id has no row: every id of an `instrument`
entry, and for an entry of kind `both` the ids marked `is_instrument` in its committed probe
output, `probes/<catalog_id>.json` (what the app prints for `SLIMPHONIC_PROBE=<file>
slimphonic`, the `plugins` of every file of the entry merged into one document; `--probes DIR`
overrides the directory). Vitalium is exempt until its ids are known.

## Contributing

An entry is accepted when the plugin is open source, has a Linux release asset
on GitHub, and loads in Slimphonic. Open an issue or a pull request against the
JSON; the app's own validation rules (https-only URLs, GitHub-hosted assets,
relative plugin paths, bounded sizes) apply.

## Licence

The catalogue data is dedicated to the public domain under CC0 1.0
(see `LICENSE`). The plugins it points to keep their own licences, named in
each entry.
