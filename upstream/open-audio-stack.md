# Corrections to send to Open Audio Stack

Prepared for `open-audio-stack/open-audio-stack-registry` (CC0), 2026-10-09. Nothing is sent
yet: the stored token cannot open pull requests. Each item names the exact OAS key (the folder
`plugins/<org>/<package>/` in the registry; `index.json` keys are `<org>/<package>`), what is
wrong in the snapshot `oas/index.json`, and the JSON to propose. Every URL, size and checksum
was downloaded and hashed on 2026-10-09. A new version is a new `<version>.yaml` file in the
package folder, with the fields of the existing newest one plus the `files` entry shown.

## A. Stale versions (the upstream release is newer than OAS lists)

### `jerryuhoo/fire` to 2.0.0

OAS lists 1.5.0; upstream tag v2.0.0 (2026) ships Fire-2.0.0-Linux.zip with CLAP and VST3. Slimphonic's pin is not in OAS (the refresh script reports it).

`plugins/jerryuhoo/fire/2.0.0.yaml`, `files` entry:

```json
{
  "systems": [
    {
      "type": "linux"
    }
  ],
  "architectures": [
    "x64"
  ],
  "contains": [
    "clap",
    "vst3"
  ],
  "type": "archive",
  "size": 24423742,
  "sha256": "d390fd0e3a432a94191c556b7a49d1b61affd0a3b5cf02b41b5bcbaf179c8a24",
  "url": "https://github.com/jerryuhoo/Fire/releases/download/v2.0.0/Fire-2.0.0-Linux.zip"
}
```

### `baconpaul/six-sines` to 1.2.1

OAS lists 1.2.0; upstream v1.2.1 is Six-Sines `six-sines-Linux-2026-07-20-18ecb36.zip`.

`plugins/baconpaul/six-sines/1.2.1.yaml`, `files` entry:

```json
{
  "systems": [
    {
      "type": "linux"
    }
  ],
  "architectures": [
    "x64"
  ],
  "contains": [
    "clap",
    "vst3"
  ],
  "type": "archive",
  "size": 28862299,
  "sha256": "9b5353eebfec3e462c80ed8c0f53c965e6262bb38537518159cce71de7eace41",
  "url": "https://github.com/baconpaul/six-sines/releases/download/v1.2.1/six-sines-Linux-2026-07-20-18ecb36.zip"
}
```

### `brummer10/neuralrack` to 0.4.1

OAS lists 0.3.3, whose Linux files do not include a CLAP archive. v0.4.1 has `NeuralRack-v0.4.1-clap-linux-x86_64.tar.xz` holding `NeuralRack.clap`.

`plugins/brummer10/neuralrack/0.4.1.yaml`, `files` entry:

```json
{
  "systems": [
    {
      "type": "linux"
    }
  ],
  "architectures": [
    "x64"
  ],
  "contains": [
    "clap"
  ],
  "type": "archive",
  "size": 2513940,
  "sha256": "6a696bfd88a7e3592bcbbf47c9c173b268091f3847b01a530e3494101ff16627",
  "url": "https://github.com/brummer10/NeuralRack/releases/download/v0.4.1/NeuralRack-v0.4.1-clap-linux-x86_64.tar.xz"
}
```

### `quamplex/geonkick` to 3.9.0

OAS lists 3.7.0; upstream v3.9.0 (2026-10-06).

`plugins/quamplex/geonkick/3.9.0.yaml`, `files` entry:

```json
{
  "systems": [
    {
      "type": "linux"
    }
  ],
  "architectures": [
    "x64"
  ],
  "contains": [
    "vst3",
    "lv2",
    "elf"
  ],
  "type": "archive",
  "size": 3767094,
  "sha256": "2ac941877bea77983677861f32cd35255fd502e2d96514702bf9e749aeb0c44c",
  "url": "https://github.com/quamplex/geonkick/releases/download/v3.9.0/GNULinux_binaries_v3.9.0_basic.zip"
}
```

### `tiagolr/filtr` to 1.3.0

OAS lists 1.1.0; upstream v1.3.0. Also: the licence in OAS is gpl-3.0, GitHub reports AGPL-3.0 for the repository (`license: agpl-3.0`).

`plugins/tiagolr/filtr/1.3.0.yaml`, `files` entry:

```json
{
  "systems": [
    {
      "type": "linux"
    }
  ],
  "architectures": [
    "x64"
  ],
  "contains": [
    "vst3",
    "lv2"
  ],
  "type": "archive",
  "size": 5487278,
  "sha256": "30840e30ed7cf323e7f8142aaba260b538fcdd531be74d2fdf796fb6f0dacfa0",
  "url": "https://github.com/tiagolr/filtr/releases/download/v1.3.0/filtr-linux-v1.3.0.zip"
}
```

### `zl-audio/zlequalizer2` to 1.4.1

OAS lists 1.3.1; upstream 1.4.1 (the AVX2 and arm64 variants exist too and need their own entries).

`plugins/zl-audio/zlequalizer2/1.4.1.yaml`, `files` entry:

```json
{
  "systems": [
    {
      "type": "linux"
    }
  ],
  "architectures": [
    "x64"
  ],
  "contains": [
    "vst3",
    "lv2"
  ],
  "type": "archive",
  "size": 10850259,
  "sha256": "ba253ef4e608e5d6f72b2c341a7bc0d9c48b79e051806c2367d481814a4dc896",
  "url": "https://github.com/ZL-Audio/ZLEqualizer/releases/download/1.4.1/ZL.Equalizer.2-1.4.1-Linux-x86-64.zip"
}
```

### `midilab/jc303` to 0.13.0

OAS lists 0.12.0; upstream v0.13.0 (2026-09-20) is a larger archive (27 MB).

`plugins/midilab/jc303/0.13.0.yaml`, `files` entry:

```json
{
  "systems": [
    {
      "type": "linux"
    }
  ],
  "architectures": [
    "x64"
  ],
  "contains": [
    "clap",
    "lv2",
    "vst3"
  ],
  "type": "archive",
  "size": 27277969,
  "sha256": "8324378f967ad1178e21411c564acb6266af7301d873f628b17bb1550f6b31f9",
  "url": "https://github.com/midilab/jc303/releases/download/v0.13.0/jc303-0.13.0-linux_x64-plugins.zip"
}
```

## B. Packages OAS does not have

Each is open source with a GitHub Linux release asset that loads in Slimphonic. Proposed
package keys follow OAS's lower-case `<org>/<package>` pattern. `files` shows the asset;
the rest (name, author, description, licence, type, tags, image) can come from the table.

### `surge-synthesizer/shortcircuit-xt` (new): Shortcircuit XT

Surge Synth Team, MIT, type `sampler`. Nightly build; rolling tag `Nightly`, so the checksum changes with every build.

```json
{
  "systems": [
    {
      "type": "linux"
    }
  ],
  "architectures": [
    "x64"
  ],
  "contains": [
    "clap",
    "vst3"
  ],
  "type": "archive",
  "size": 39432421,
  "sha256": "dca5cf40b9c3c91d96f7f406656eff7eafdedca46a7d57e017113e93b32ec963",
  "url": "https://github.com/surge-synthesizer/shortcircuit-xt/releases/download/Nightly/shortcircuit-xt-linux-2026-10-08-24e4feb.zip"
}
```

### `distrho/ildaeil` (new): Ildaeil

DISTRHO, GPL-2.0, type `effect`. Plugin host that runs other plugin formats; CLAP bundle directory `Ildaeil.clap/`.

```json
{
  "systems": [
    {
      "type": "linux"
    }
  ],
  "architectures": [
    "x64"
  ],
  "contains": [
    "clap",
    "vst3",
    "lv2"
  ],
  "type": "archive",
  "size": 75458065,
  "sha256": "367e43ae7c36db3feb740f059b704980c8fc5376f93114a7c03c353c8db67f34",
  "url": "https://github.com/DISTRHO/Ildaeil/releases/download/v1.3/Ildaeil-linux-x86_64-v1.3.zip"
}
```

### `brummer10/ratatouille` (new): Ratatouille

brummer10, BSD-3-Clause, type `effect`. Repository `brummer10/Ratatouille.lv2`.

```json
{
  "systems": [
    {
      "type": "linux"
    }
  ],
  "architectures": [
    "x64"
  ],
  "contains": [
    "clap"
  ],
  "type": "archive",
  "size": 2089248,
  "sha256": "132b554a04abacf77867bd2335f02294069424ee73cd23531f3a97b5ef040f06",
  "url": "https://github.com/brummer10/Ratatouille.lv2/releases/download/v0.9.11/Ratatouille.lv2-clap-v0.9.11-linux-x86_64.tar.xz"
}
```

### `surge-synthesizer/stochas` (new): Stochas

Surge Synth Team, GPL-3.0, type `tool`. A note effect (probabilistic sequencer).

```json
{
  "systems": [
    {
      "type": "linux"
    }
  ],
  "architectures": [
    "x64"
  ],
  "contains": [
    "clap",
    "vst3"
  ],
  "type": "archive",
  "size": 10917720,
  "sha256": "c552d9d63c7e09e5d781d1d5c71b7fe389f2940c8a18b888ef22beebe6e4807c",
  "url": "https://github.com/surge-synthesizer/stochas/releases/download/v1.3.13/stochas-1.3.13.360d5ca.linux-x86_64.tgz"
}
```

### `trummerschlunk/master-me` (new): master_me

Klaus Scheuermann, GPL-3.0, type `effect`. Ships both formats; OAS has no package for it.

```json
{
  "systems": [
    {
      "type": "linux"
    }
  ],
  "architectures": [
    "x64"
  ],
  "contains": [
    "clap",
    "vst3",
    "lv2"
  ],
  "type": "archive",
  "size": 2342208,
  "sha256": "09f41b4607ea66fd1d2f69c6b2e92ad4a36cd748c9e6da9a39b7e802c143d6a2",
  "url": "https://github.com/trummerschlunk/master_me/releases/download/1.3.1/master_me-1.3.1-linux-x86_64.tar.xz"
}
```

### `baconpaul/airwindows-consolidated` (new): Airwindows Consolidated

baconpaul, MIT, type `effect`. About 400 Airwindows effects in one plugin; rolling tag `DAWPlugin`. OAS has `airwindows/airwindows` (a different, older packaging).

```json
{
  "systems": [
    {
      "type": "linux"
    }
  ],
  "architectures": [
    "x64"
  ],
  "contains": [
    "clap",
    "vst3",
    "lv2"
  ],
  "type": "archive",
  "size": 32477404,
  "sha256": "1b0ecf04c418087f84849d85e5c67e8703642d99a423429fce5a11b929f66780",
  "url": "https://github.com/baconpaul/airwin2rack/releases/download/DAWPlugin/AirwindowsConsolidated-2026-10-04-9b87116-Linux.zip"
}
```

## C. Wrong or missing metadata

- `chowdhury-dsp/chowtapemodel` 2.11.4: the `contains` of `ChowTapeModel-Linux-x64-2.11.4.deb` omits
  `clap`; the deb holds `usr/lib/clap/CHOWTapeModel.clap` (CLAP id `org.chowdsp.CHOWTapeModel`).
  Proposed `"contains": ["clap", "vst3", "lv2", "elf", "so"]`.
- `tytel/vital` (and any package whose `image` points at a missing file): the image URL answered
  404 on 2026-10-09; check that the `vital.jpg` is committed or drop the field.
- `surge-synthesizer/monique-monosynth` 1.2.0: the Linux asset is the rolling `Nightly` tag
  (`MoniqueMonosynth-2024-08-07-df7d339-Linux.zip`); its checksum will drift when the tag is rebuilt.
- `midilab/jc303`: see A. `distrho/cardinal` is correct (version `2026.2.0` for tag `26.02`,
  sha256 `657df0be...` verified).

## D. Not OAS, but upstream bugs found while probing (for the projects' own trackers)

- DPF-Plugins 1.7: the CLAP descriptors of `3BandEQ`, `3BandSplitter` and `PingPongPan` all carry the
  id `studio.kx.distrho.MVerb`, MVerb's own. A host that dedupes by CLAP id loads only one of the four.
- Shortcircuit XT nightly 2026-10-08 and Six Sines 1.2.1: the VST3 bundle aborts when loaded by a bare
  host (a core dump in Slimphonic's probe child); the CLAP loads fine.
- LSP Plugins 1.2.35: the VST3 bundle's `Contents/x86_64-linux/` holds `liblsp-r3d-glx-lib.so`
  beside the module, and a scan that takes the first `.so` loads the wrong file.
