#!/usr/bin/env python3
"""Builds linux.json from the vendored Open Audio Stack snapshot plus the overlay.

    python3 -I tools/catalog_refresh.py --oas oas/index.json --overlay overlay/ --hidden hidden.json \
        --categories categories.json --out linux.json

Open Audio Stack (CC0) supplies what it knows (name, author, type, licence, homepage, image);
the overlay (overlay/<catalog_id>.json) supplies what it cannot (archive paths, pinned
sha256/size, companions, our description, editor's pick, ...) and always wins. This script
never touches the network: the snapshot is refreshed by hand (see oas/SNAPSHOT.md). The last
step is a validator that mirrors the app's `manifest::validate`.

Instrument categories come from two places: a per-entry map in the overlay next to the ids it
describes (`formats.clap.categories`, or `formats.vst3.categories` for a VST3-only entry) and
`categories.json` for plugins outside the catalogue (the bundled Slim instruments). Both are
merged into the manifest's top-level `categories` list; the per-format maps are not emitted.
Every instrument id must have a row: all ids of an `instrument` entry, and for a `both` entry
the ids its committed probe output (`probes/<catalog_id>.json`, the `SLIMPHONIC_PROBE` JSON)
marks `is_instrument`.
"""

import argparse
import datetime
import json
import re
import sys
from pathlib import Path

SCHEMA_VERSION = 1
MIN_APP_VERSION = "0.7.0"
DEFAULT_PLATFORM = "linux-x86_64"

# platform key -> (OAS system type, OAS architecture)
PLATFORMS = {"linux-x86_64": ("linux", "x64")}

# OAS has five plugin types; the manifest has instrument / effect / both.
KIND_OF_TYPE = {
    "instrument": "instrument",
    "sampler": "instrument",
    "generator": "instrument",
    "effect": "effect",
    "tool": "effect",
}

SPDX_IDS = [
    "GPL-2.0", "GPL-3.0", "LGPL-2.1", "LGPL-3.0", "AGPL-3.0", "MIT", "ISC", "Apache-2.0",
    "BSD-2-Clause", "BSD-3-Clause", "BSL-1.0", "CC0-1.0", "CC-BY-4.0", "CC-BY-SA-4.0",
    "Unlicense", "0BSD", "Zlib",
]
_SPDX_BY_LOWER = {s.lower(): s for s in SPDX_IDS}
_GPL_FAMILY = re.compile(r"^(a|l)?gpl[- ]?v?(\d)(?:\.(\d))?(\+|-or-later|-only)?$")

# Key order of every object, as the app's file has always been written.
ENTRY_KEYS = [
    "catalog_id", "name", "vendor", "kind", "experimental", "rolling_tag", "license",
    "description", "image", "homepage", "source", "github", "score", "formats", "content",
    "install",
]
INSTALL_KEYS = [
    "kind", "version", "url", "sha256", "size_bytes", "archive", "companions", "min_glibc",
    "distro_hint", "post_install_notes", "link_url", "link_label", "data",
]
# Install keys written only when the overlay sets them (the app reads them as absent = none).
OPTIONAL_INSTALL_KEYS = ("data",)
LICENSE_KEYS = ["spdx", "url", "kind"]
LICENSE_KINDS = ("open-source", "free-closed-source")
HIDDEN_KEYS = ["key", "name"]
CATEGORY_KEYS = ["key", "name", "category"]
# The app's `PluginCategory` ids (src/plugin_category.rs), in Browser order.
CATEGORY_IDS = (
    "subtractive", "wavetable", "fm", "additive", "physical", "keys", "sampler", "drums",
    "modular", "other",
)
# Instrument entries whose ids are not known yet (no binary release to probe).
COVERAGE_EXEMPT = {"vitalium": "no ids until probed from the distro package"}
ROLLING_TAGS = ("nightly", "latest", "dawplugin")


# ---- OAS field mappings -------------------------------------------------------------------


def normalise_license(raw):
    """An OAS licence string as an SPDX id, or None when it is not unambiguous."""
    if not isinstance(raw, str):
        return None
    s = raw.strip().lower()
    if s in _SPDX_BY_LOWER:
        return _SPDX_BY_LOWER[s]
    m = _GPL_FAMILY.match(s)
    if m:
        prefix, major, minor = (m.group(1) or ""), m.group(2), m.group(3) or "0"
        candidate = f"{prefix.upper()}GPL-{major}.{minor}"
        if candidate.lower() in _SPDX_BY_LOWER:
            return _SPDX_BY_LOWER[candidate.lower()]
    return None  # "other", free text, expressions: the overlay has to say


def kind_of(oas_type):
    return KIND_OF_TYPE.get(oas_type)


def _version_key(v):
    return tuple(int(p) if p.isdigit() else 0 for p in re.split(r"[.\-]", v))


def latest_version(package):
    """The version object a package names as its latest (its top-level `version`); when that
    key is missing from `versions`, the highest version number."""
    versions = package.get("versions") or {}
    name = package.get("version")
    if name in versions:
        return name, versions[name]
    if not versions:
        return None, None
    name = max(versions, key=_version_key)
    return name, versions[name]


def files_for_platform(version_obj, platform):
    """The files of a version built for `platform`. OAS `systems` is a list of objects
    (`{"type": "linux"}`, sometimes with a `min`), not strings."""
    system, arch = PLATFORMS[platform]
    out = []
    for f in version_obj.get("files", []):
        systems = {s.get("type") for s in f.get("systems", []) if isinstance(s, dict)}
        if system in systems and arch in f.get("architectures", []):
            out.append(f)
    return out


def is_rolling_url(url):
    """A release tag that upstream overwrites in place."""
    m = re.search(r"/releases/download/([^/]+)/", url or "")
    return bool(m) and m.group(1).lower() in ROLLING_TAGS


def drift(overlay, version_obj, platform):
    """Human-readable differences between the overlay's pinned asset and what OAS lists now.
    Informational: the overlay's pin is what ships."""
    pin = (overlay.get("install") or {}).get(platform) or {}
    if not pin.get("url") or version_obj is None:
        return []
    for f in files_for_platform(version_obj, platform):
        if f.get("url") == pin["url"]:
            if f.get("sha256") != pin["sha256"]:
                note = "rolling tag, expected" if overlay.get("rolling_tag") else "CHANGED"
                return [f"{overlay['catalog_id']}: OAS sha256 differs from the pin ({note})"]
            return []
    return [f"{overlay['catalog_id']}: pinned url not listed in OAS for {platform}"]


def trim_description(text, limit=600):
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


# ---- building -----------------------------------------------------------------------------


def base_entry(overlay, oas):
    """What OAS alone yields for an entry (empty when it has no OAS package)."""
    oas_id = overlay.get("oas_id")
    if not oas_id:
        return {}
    package = oas["plugins"].get(oas_id)
    if package is None:
        raise KeyError(f"{overlay['catalog_id']}: oas_id {oas_id!r} is not in the OAS snapshot")
    _, v = latest_version(package)
    if v is None:
        return {}
    base = {"name": v.get("name"), "vendor": v.get("author"), "kind": kind_of(v.get("type"))}
    base["description"] = trim_description(v.get("description"))
    base["homepage"] = v.get("url")
    base["source"] = v.get("url")
    if v.get("image"):
        base["image"] = {"url": v["image"], "sha256": ""}
    spdx = normalise_license(v.get("license"))
    if spdx:
        base["license"] = {"spdx": spdx, "url": v.get("url")}
    return {k: val for k, val in base.items() if val is not None}


def build_entry(overlay, oas, platform):
    e = base_entry(overlay, oas)
    for key in ("name", "vendor", "kind", "description", "homepage", "source", "image"):
        if key in overlay:
            e[key] = overlay[key]
    # The licence url follows the entry's source unless the overlay names its own.
    lic = dict(e.get("license") or {})
    lic.update(overlay.get("license") or {})
    if "spdx" in lic and "url" not in (overlay.get("license") or {}):
        lic["url"] = e.get("source")
    # Open source unless the overlay says free closed source (and then names no source).
    lic.setdefault("kind", "open-source")
    e["license"] = {k: lic.get(k) for k in LICENSE_KEYS}
    e.setdefault("source", None)
    e.setdefault("image", None)
    e["catalog_id"] = overlay["catalog_id"]
    e["experimental"] = overlay["experimental"]
    e["rolling_tag"] = overlay["rolling_tag"]
    e["github"] = overlay.get("github")
    e["score"] = {
        "editors_pick": overlay["editors_pick"],
        "note": overlay["score_note"],
        "tested_with": overlay.get("tested_with"),
    }
    e["formats"] = _formats_without_categories(overlay["formats"])
    e["content"] = overlay.get("content")
    pin = overlay["install"][platform]
    e["install"] = {platform: {k: pin.get(k) for k in INSTALL_KEYS
                               if k not in OPTIONAL_INSTALL_KEYS or pin.get(k) is not None}}
    e["install"][platform]["companions"] = list(pin.get("companions") or [])
    return {k: e[k] for k in ENTRY_KEYS}


def _formats_without_categories(formats):
    """The overlay's formats as the manifest carries them: the category maps live only in the
    top-level `categories` list."""
    if formats is None:
        return None
    return {fmt: None if block is None else {k: v for k, v in block.items() if k != "categories"}
            for fmt, block in formats.items()}


def load_overlays(directory):
    overlays = [json.loads(p.read_text("utf-8")) for p in sorted(Path(directory).glob("*.json"))]
    overlays.sort(key=lambda o: (o["order"], o["catalog_id"]))
    return overlays


def load_hidden(path):
    return json.loads(Path(path).read_text("utf-8"))


def load_categories(path):
    return json.loads(Path(path).read_text("utf-8"))


def load_probes(directory):
    """`probes/<catalog_id>.json` by catalog id (an absent directory is no probes)."""
    d = Path(directory)
    if not d.is_dir():
        return {}
    return {p.stem: json.loads(p.read_text("utf-8")) for p in sorted(d.glob("*.json"))}


class CategoryError(Exception):
    """The curated categories are inconsistent: one message per problem."""

    def __init__(self, errors):
        super().__init__("\n".join(errors))
        self.errors = errors


def _instrument_ids(entry, probes):
    """(format, ids) that need a category row; None when the entry is exempt. A dual-format
    entry is categorised under its CLAP ids, a VST3-only one under its class ids."""
    clap, vst3 = entry["formats"]["clap"], entry["formats"]["vst3"]
    if clap is not None and clap["plugin_ids"]:
        fmt, ids = "clap", clap["plugin_ids"]
    else:
        fmt, ids = "vst3", (vst3 or {}).get("class_ids") or []
    if entry["kind"] == "effect":
        return fmt, set()
    if entry["catalog_id"] in COVERAGE_EXEMPT:
        return None
    if entry["kind"] == "instrument":
        return fmt, set(ids)
    probe = probes.get(entry["catalog_id"])
    if probe is None:
        raise CategoryError([f"{entry['catalog_id']}: an entry of kind both needs "
                             f"probes/{entry['catalog_id']}.json"])
    return fmt, {p["id"] for p in probe["plugins"] if p["is_instrument"]}


def category_rows(overlays, entries, extra, probes):
    """The manifest's `categories` list: the overlay maps plus `extra` (categories.json), sorted
    by key. Raises `CategoryError` for an unknown category, a map key its format does not list,
    a key with two rows, an entry of kind both without a probe or an instrument id without a
    row."""
    errors, rows = [], {}
    by_id = {e["catalog_id"]: e for e in entries}

    def add(key, name, category, where):
        if category not in CATEGORY_IDS:
            errors.append(f"{where}: {key}: unknown category {category!r}")
        if key in rows:
            errors.append(f"{where}: {key}: has two category rows")
        rows[key] = {"key": key, "name": name, "category": category}

    for o in overlays:
        entry = by_id.get(o["catalog_id"])
        if entry is None:
            continue
        probe = probes.get(o["catalog_id"]) or {"plugins": []}
        probed_names = {p["id"]: p["name"] for p in probe["plugins"]}
        covered = set()
        for fmt, ids_field, prefix in (("clap", "plugin_ids", "clap:"),
                                       ("vst3", "class_ids", "vst3:")):
            block = (o.get("formats") or {}).get(fmt)
            if not block or "categories" not in block:
                continue
            for pid, category in block["categories"].items():
                if pid not in block[ids_field]:
                    errors.append(f"{o['catalog_id']}: formats.{fmt}.categories: {pid!r} is not "
                                  f"one of its {ids_field}")
                key = prefix + (pid.lower() if fmt == "vst3" else pid)
                add(key, probed_names.get(pid, entry["name"]), category, o["catalog_id"])
                covered.add((fmt, pid))
        try:
            needed = _instrument_ids(entry, probes)
        except CategoryError as e:
            errors.extend(e.errors)
            continue
        if needed is None:
            continue
        fmt, ids = needed
        for pid in sorted(ids - {p for f, p in covered if f == fmt}):
            errors.append(f"{o['catalog_id']}: instrument {pid!r} has no category "
                          f"(formats.{fmt}.categories)")
    for row in extra:
        add(row["key"], row["name"], row["category"], "categories.json")
    if errors:
        raise CategoryError(errors)
    return [rows[k] for k in sorted(rows)]


def build(oas, overlays, platform, date, hidden, categories, probes):
    plugins = [build_entry(o, oas, platform) for o in overlays if platform in o["install"]]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": date,
        "min_app_version": MIN_APP_VERSION,
        "plugins": plugins,
        "hidden": [{k: h[k] for k in HIDDEN_KEYS} for h in hidden],
        "categories": category_rows(overlays, plugins, categories, probes),
    }


def render(manifest):
    return json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"


# ---- validator: mirrors src/web_catalog/manifest.rs ---------------------------------------

MAX_ENTRIES, MAX_PATHS, MAX_NAME, MAX_DESCRIPTION, MAX_URL, MAX_PATH, MAX_TEXT = (
    500, 16, 80, 600, 512, 256, 300)
MAX_ARCHIVE_BYTES = 4 * 1024**3
# Also the hosts a download may be redirected to (u-he's CDN and its own site).
ASSET_HOSTS = ("github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com",
               "tal-software.com", "cdn1.resources.manda-audio.com", "dl.u-he.com",
               "uhe-dl.b-cdn.net", "u-he.com", "www.auburnsounds.com")
ARCHIVES = ("tar.gz", "tar.xz", "tgz", "zip", "7z", "deb", "none")
INSTALL_KINDS = ("github-release-asset", "deb-asset", "vendor-download", "manual-link")
PLUGIN_KEY = re.compile(r"clap:[^\x00-\x1f\x7f]{1,256}|vst3:[0-9a-f]{32}|ladspa:[0-9]{1,20}")
INSTALL_TO = ("ClapDir", "Vst3Dir", "SurgeData", "UHeData")
PRODUCT_NAME = re.compile(r"[A-Za-z0-9 ._-]{1,64}")


class _Checker:
    def __init__(self):
        self.errors = []
        self.context = ""

    def fail(self, what, why):
        self.errors.append(f"{self.context}: {what}: {why}" if self.context else f"{what}: {why}")

    def bounded(self, what, s, limit):
        if not isinstance(s, str):
            return self.fail(what, "must be a string")
        if len(s) > limit:
            self.fail(what, f"longer than {limit} characters")
        if any((ord(c) < 32 and c != "\n") or 0x7F <= ord(c) < 0xA0 for c in s):
            self.fail(what, "contains a control character")

    def text(self, what, s, limit):
        if s == "":
            self.fail(what, "must not be empty")
        self.bounded(what, s, limit)

    def opt_text(self, what, s, limit):
        if s is not None:
            self.text(what, s, limit)

    def https_url(self, what, url):
        self.bounded(what, url, MAX_URL)
        if not isinstance(url, str) or not url.startswith("https://"):
            self.fail(what, "must start with https://")
            return None
        if re.search(r"[\s\\]", url):
            self.fail(what, "contains whitespace or a backslash")
        host = re.split(r"[/?#]", url[len("https://"):])[0]
        if not host or "@" in host or ":" in host:
            self.fail(what, "has no plain host name")
            return None
        if ".." in url:
            self.fail(what, "must not contain ..")
        return host

    def asset_url(self, what, url):
        host = self.https_url(what, url)
        if host is not None and host not in ASSET_HOSTS:
            self.fail(what, f"host {host} is not an allowed download host")

    def sha256(self, what, s, may_be_empty):
        ok = isinstance(s, str) and re.fullmatch(r"[0-9a-f]{64}", s) is not None
        if not ok and not (may_be_empty and s == ""):
            self.fail(what, "must be 64 lowercase hex digits")

    def date(self, what, s):
        if not (isinstance(s, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", s)):
            self.fail(what, "must be a YYYY-MM-DD date")

    def size(self, what, n):
        if not isinstance(n, int) or isinstance(n, bool) or n == 0 or n > MAX_ARCHIVE_BYTES:
            self.fail(what, "must be between 1 byte and 4 GiB")

    def glob(self, what, g, extension):
        why = None
        if not isinstance(g, str) or g == "" or len(g) > MAX_PATH:
            why = "empty or too long"
        elif any(ord(c) < 32 or c == "\\" for c in g):
            why = "control character or backslash"
        elif g.startswith("/"):
            why = "must be relative"
        elif ".." in g:
            why = "must not contain .."
        elif "**" in g:
            why = "** is not supported"
        elif any(c in g for c in "?[]{}"):
            why = "only * is a wildcard"
        elif any(part in ("", ".") for part in g.split("/")):
            why = "empty or . path component"
        if why:
            self.fail(what, f"bad path {g!r}: {why}")
        elif extension and not g.endswith(extension):
            self.fail(what, f"path {g!r} must end with {extension}")

    def paths(self, what, paths, extension):
        if len(paths) > MAX_PATHS:
            self.fail(what, f"more than {MAX_PATHS} paths")
        for p in paths[:MAX_PATHS]:
            self.glob(what, p, extension)

    def keys(self, what, obj, allowed):
        if not isinstance(obj, dict):
            self.fail(what, "must be an object")
            return False
        for k in obj:
            if k not in allowed:
                self.fail(what, f"unknown field {k!r}")
        for k in allowed:
            if k not in obj and k not in ("rolling_tag", "companions") + OPTIONAL_INSTALL_KEYS:
                self.fail(what, f"missing field {k!r}")
        return True


def validate(text):
    """Returns the list of problems with a manifest (empty = valid)."""
    try:
        data = json.loads(text)
    except ValueError as e:
        return [f"not a catalogue manifest: {e}"]
    c = _Checker()
    if not isinstance(data, dict) or not isinstance(data.get("schema_version"), int):
        return ["not a catalogue manifest: no schema_version"]
    if data["schema_version"] > SCHEMA_VERSION:
        return [f"schema_version {data['schema_version']} is newer than this app understands"]
    if not c.keys("catalogue", data, ["schema_version", "generated_at", "min_app_version", "plugins",
                          "hidden", "categories"]):
        return c.errors
    c.date("generated_at", data["generated_at"])
    if not re.fullmatch(r"\d+\.\d+\.\d+", str(data["min_app_version"])):
        c.fail("min_app_version", "must look like 1.2.3")
    plugins = data["plugins"]
    if not isinstance(plugins, list):
        return c.errors + ["plugins: must be a list"]
    if len(plugins) > MAX_ENTRIES:
        return c.errors + [f"plugins: more than {MAX_ENTRIES} entries"]
    _hidden(c, data["hidden"])
    _categories(c, data["categories"])
    c.context = ""
    seen = set()
    for e in plugins:
        c.context = ""
        if not isinstance(e, dict):
            c.fail("plugin", "must be an object")
            continue
        cid = e.get("catalog_id", "")
        if cid in seen:
            c.fail("catalog_id", f"{cid!r} appears twice")
        seen.add(cid)
        c.context = str(cid)
        _entry(c, e)
    return c.errors


def _hidden(c, hidden):
    """The Editor-hidden list: PluginKey syntax (see src/plugin_key.rs), unique keys."""
    c.context = "hidden"
    if not isinstance(hidden, list):
        return c.fail("hidden", "must be a list")
    if len(hidden) > MAX_ENTRIES:
        return c.fail("hidden", f"more than {MAX_ENTRIES} entries")
    seen = set()
    for h in hidden:
        if not c.keys("hidden entry", h, HIDDEN_KEYS):
            continue
        key = h["key"]
        if not (isinstance(key, str) and PLUGIN_KEY.fullmatch(key)):
            c.fail("key", f"{key!r} is not clap:<id>, vst3:<32 hex> or ladspa:<number>")
        elif key in seen:
            c.fail("key", f"{key!r} appears twice")
        seen.add(key)
        c.text("name", h["name"], MAX_NAME)


def _categories(c, rows):
    """The curated plugin categories: PluginKey syntax, a known category, unique keys."""
    c.context = "categories"
    if not isinstance(rows, list):
        return c.fail("categories", "must be a list")
    if len(rows) > MAX_ENTRIES:
        return c.fail("categories", f"more than {MAX_ENTRIES} entries")
    seen = set()
    for r in rows:
        if not c.keys("category entry", r, CATEGORY_KEYS):
            continue
        key = r["key"]
        if not (isinstance(key, str) and PLUGIN_KEY.fullmatch(key)):
            c.fail("key", f"{key!r} is not clap:<id>, vst3:<32 hex> or ladspa:<number>")
        elif key in seen:
            c.fail("key", f"{key!r} appears twice")
        seen.add(key)
        c.text("name", r["name"], MAX_NAME)
        if r["category"] not in CATEGORY_IDS:
            c.fail("category", f"{r['category']!r} is not a known category")


def _entry(c, e):
    if not c.keys("entry", e, ENTRY_KEYS):
        return
    cid = e["catalog_id"]
    if not (isinstance(cid, str) and re.fullmatch(r"[a-z0-9-]{1,64}", cid)):
        c.fail("catalog_id", "must be 1-64 characters of [a-z0-9-]")
    c.text("name", e["name"], MAX_NAME)
    c.text("vendor", e["vendor"], MAX_NAME)
    if e["kind"] not in ("instrument", "effect", "both"):
        c.fail("kind", "must be instrument, effect or both")
    for flag in ("experimental", "rolling_tag"):
        if flag in e and not isinstance(e[flag], bool):
            c.fail(flag, "must be a bool")
    c.text("description", e["description"], MAX_DESCRIPTION)
    if c.keys("license", e["license"], LICENSE_KEYS):
        c.text("license.spdx", e["license"]["spdx"], MAX_TEXT)
        c.https_url("license.url", e["license"]["url"])
        kind = e["license"].get("kind")
        if kind not in LICENSE_KINDS:
            c.fail("license.kind", f"{kind!r} is not open-source or free-closed-source")
        elif kind == "open-source" and e["source"] is None:
            c.fail("source", "open source needs one")
        elif kind == "free-closed-source" and e["source"] is not None:
            c.fail("source", "a closed-source entry has none")
    c.https_url("homepage", e["homepage"])
    if e["source"] is not None:
        c.https_url("source", e["source"])
    if c.keys("score", e["score"], ["editors_pick", "note", "tested_with"]):
        if not isinstance(e["score"]["editors_pick"], bool):
            c.fail("score.editors_pick", "must be a bool")
        c.bounded("score.note", e["score"]["note"], MAX_DESCRIPTION)
        c.opt_text("score.tested_with", e["score"]["tested_with"], MAX_TEXT)
    if e["image"] is not None and c.keys("image", e["image"], ["url", "sha256"]):
        c.https_url("image.url", e["image"]["url"])
        c.sha256("image.sha256", e["image"]["sha256"], True)
    gh = e["github"]
    if gh is not None and c.keys("github", gh, ["owner", "repo", "snapshot"]):
        c.text("github.owner", gh["owner"], MAX_NAME)
        c.text("github.repo", gh["repo"], MAX_NAME)
        snap = gh["snapshot"]
        if c.keys("github.snapshot", snap, ["stars", "pushed_at", "latest_release", "at"]):
            if snap["stars"] is not None and not (isinstance(snap["stars"], int) and snap["stars"] >= 0):
                c.fail("github.snapshot.stars", "must be a non-negative integer or null")
            c.text("github.snapshot.latest_release", snap["latest_release"], MAX_TEXT)
            c.date("github.snapshot.at", snap["at"])
            c.opt_text("github.snapshot.pushed_at", snap["pushed_at"], 40)
    content = e["content"]
    if content is not None and c.keys("content", content, ["note", "url", "sha256", "size_bytes", "install_to"]):
        c.text("content.note", content["note"], MAX_TEXT)
        c.asset_url("content.url", content["url"])
        c.sha256("content.sha256", content["sha256"], False)
        c.size("content.size_bytes", content["size_bytes"])
        if content["install_to"] not in INSTALL_TO:
            c.fail("content.install_to", "unknown location")
        elif content["install_to"] == "UHeData":
            c.fail("content.install_to", "UHeData is only for install.data")
    installs = e["install"]
    if not isinstance(installs, dict) or not installs:
        c.fail("install", "needs at least one platform")
        installs = {}
    installable = False
    for platform, i in installs.items():
        if not re.fullmatch(r"[a-z0-9_-]{1,32}", platform):
            c.fail("install", f"odd platform key {platform!r}")
        if isinstance(i, dict):
            installable |= i.get("kind") != "manual-link"
        _install(c, platform, i)
    data = next((i["data"] for i in installs.values()
                 if isinstance(i, dict) and isinstance(i.get("data"), dict)), None)
    _formats(c, e["formats"], installable, data)


def _formats(c, f, installable, data=None):
    """`data`: the entry's data folder; its library paths are then `.so` files inside it."""
    if not c.keys("formats", f, ["clap", "vst3"]):
        return
    clap, vst3 = f["clap"], f["vst3"]
    clap_ext, vst3_ext = (".so", ".so") if data else (".clap", ".vst3")
    if clap is not None and c.keys("formats.clap", clap, ["plugin_ids", "features", "paths"]):
        for i in clap["plugin_ids"][:MAX_ENTRIES]:
            c.text("formats.clap.plugin_ids", i, MAX_TEXT)
        for i in clap["features"][:MAX_ENTRIES]:
            c.text("formats.clap.features", i, MAX_NAME)
        c.paths("formats.clap.paths", clap["paths"], clap_ext)
    if vst3 is not None and c.keys("formats.vst3", vst3, ["class_ids", "bundles"]):
        for i in vst3["class_ids"][:MAX_ENTRIES]:
            if not (isinstance(i, str) and re.fullmatch(r"[0-9a-fA-F]{32}", i)):
                c.fail("formats.vst3.class_ids", f"{i!r} is not 32 hex digits")
        c.paths("formats.vst3.bundles", vst3["bundles"], vst3_ext)
    if clap and vst3:
        a, b = len(clap["plugin_ids"]), len(vst3["class_ids"])
        if a and b and a != b:
            c.fail("formats", "plugin_ids and class_ids must be index-aligned")
    if installable:
        n_clap = len(clap["paths"]) if clap is not None else None
        n_vst3 = len(vst3["bundles"]) if vst3 is not None else None
        if (n_clap or 0) + (n_vst3 or 0) == 0:
            c.fail("formats", "an installable entry needs at least one path")
        if n_clap == 0 or n_vst3 == 0:
            c.fail("formats", "a listed format needs at least one path")
    if data and isinstance(data.get("path"), str):
        for block, field in ((clap, "paths"), (vst3, "bundles")):
            if block is None:
                continue
            if len(block[field]) != 1:
                c.fail("formats", "a data-folder entry has one library path per format")
            for path in block[field]:
                if not path.startswith(data["path"] + "/"):
                    c.fail("formats", f"{path!r} is not inside the data folder {data['path']!r}")


def _install(c, platform, i):
    what = f"install.{platform}"
    if not c.keys(what, i, INSTALL_KEYS):
        return
    w = lambda field: f"{what}.{field}"  # noqa: E731
    c.opt_text(w("version"), i["version"], 40)
    c.opt_text(w("min_glibc"), i["min_glibc"], 16)
    c.opt_text(w("distro_hint"), i["distro_hint"], MAX_TEXT)
    c.opt_text(w("post_install_notes"), i["post_install_notes"], MAX_DESCRIPTION)
    c.opt_text(w("link_label"), i["link_label"], MAX_NAME)
    if len(i["companions"]) > MAX_PATHS:
        c.fail(w("companions"), f"more than {MAX_PATHS}")
    for comp in i["companions"][:MAX_PATHS]:
        c.glob(w("companions"), comp, None)
    if i["kind"] not in INSTALL_KINDS:
        c.fail(w("kind"), "unknown install kind")
    if i["archive"] not in ARCHIVES:
        c.fail(w("archive"), "unknown archive kind")
    if i["kind"] == "manual-link":
        if i["link_url"] is None:
            c.fail(w("link_url"), "a manual-link needs one")
        else:
            c.https_url(w("link_url"), i["link_url"])
        if i["url"] is not None or i["sha256"] is not None or i["size_bytes"] is not None:
            c.fail(what, "a manual-link has no url, sha256 or size_bytes")
        if i["archive"] != "none":
            c.fail(w("archive"), 'a manual-link has archive "none"')
    elif i["kind"] in ("github-release-asset", "deb-asset", "vendor-download"):
        if i["link_url"] is not None or i["link_label"] is not None:
            c.fail(what, "only a manual-link has link_url or link_label")
        if i["url"] is None:
            c.fail(w("url"), "missing")
        else:
            c.asset_url(w("url"), i["url"])
        if i["sha256"] is None:
            c.fail(w("sha256"), "missing")
        else:
            c.sha256(w("sha256"), i["sha256"], False)
        if i["size_bytes"] is None:
            c.fail(w("size_bytes"), "missing")
        else:
            c.size(w("size_bytes"), i["size_bytes"])
        if i["version"] is None:
            c.fail(w("version"), "missing")
        ok = i["archive"] == "deb" if i["kind"] == "deb-asset" else i["archive"] not in ("deb", "none")
        if not ok:
            c.fail(w("archive"), "does not fit the install kind")
    data = i.get("data")
    if data is not None and c.keys(w("data"), data, ["install_to", "path"]):
        if i["kind"] == "manual-link":
            c.fail(w("data"), "a manual-link installs nothing")
        if data["install_to"] != "UHeData":
            c.fail(w("data.install_to"), "only UHeData takes a data folder")
        c.glob(w("data.path"), data["path"], None)
        name = str(data["path"]).rsplit("/", 1)[-1]
        if not PRODUCT_NAME.fullmatch(name) or name.startswith("."):
            c.fail(w("data.path"), "must end in a plain folder name (letters, digits, space . _ -)")


# ---- command line -------------------------------------------------------------------------


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--oas", required=True, help="OAS index.json snapshot")
    ap.add_argument("--overlay", required=True, help="directory of overlay/<catalog_id>.json")
    ap.add_argument("--hidden", required=True, help="hidden.json, the Editor-hidden plugin keys")
    ap.add_argument("--categories", required=True,
                    help="categories.json, instrument categories of plugins outside the catalogue")
    ap.add_argument("--probes", default=None,
                    help="directory of <catalog_id>.json probe outputs (default: probes/ beside "
                         "--overlay)")
    ap.add_argument("--out", required=True, help="manifest to write")
    ap.add_argument("--platform", default=DEFAULT_PLATFORM, choices=sorted(PLATFORMS))
    ap.add_argument("--date", default=None, help="generated_at (default: today)")
    args = ap.parse_args(argv)
    date = args.date or datetime.date.today().isoformat()
    oas = json.loads(Path(args.oas).read_text("utf-8"))
    overlays = load_overlays(args.overlay)
    for o in overlays:
        package = oas["plugins"].get(o.get("oas_id") or "")
        if package is not None:
            for line in drift(o, latest_version(package)[1], args.platform):
                print("note:", line, file=sys.stderr)
    probes_dir = args.probes or Path(args.overlay).resolve().parent / "probes"
    try:
        manifest = build(oas, overlays, args.platform, date, load_hidden(args.hidden),
                         load_categories(args.categories), load_probes(probes_dir))
    except CategoryError as e:
        print("the instrument categories are inconsistent:", *e.errors, sep="\n  ",
              file=sys.stderr)
        return 1
    text = render(manifest)
    errors = validate(text)
    if errors:
        print("the generated manifest is invalid:", *errors, sep="\n  ", file=sys.stderr)
        return 1
    Path(args.out).write_text(text, "utf-8")
    print(f"wrote {args.out}: {len(overlays)} entries, valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
