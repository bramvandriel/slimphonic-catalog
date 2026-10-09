#!/usr/bin/env python3
"""Builds linux.json from the vendored Open Audio Stack snapshot plus the overlay.

    python3 -I tools/catalog_refresh.py --oas oas/index.json --overlay overlay/ --out linux.json

Open Audio Stack (CC0) supplies what it knows (name, author, type, licence, homepage, image);
the overlay (overlay/<catalog_id>.json) supplies what it cannot (archive paths, pinned
sha256/size, companions, our description, editor's pick, ...) and always wins. This script
never touches the network: the snapshot is refreshed by hand (see oas/SNAPSHOT.md). The last
step is a validator that mirrors the app's `manifest::validate`.
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
    "distro_hint", "post_install_notes", "link_url", "link_label",
]
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
    e["license"] = lic
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
    e["formats"] = overlay["formats"]
    e["content"] = overlay.get("content")
    pin = overlay["install"][platform]
    e["install"] = {platform: {k: pin.get(k) for k in INSTALL_KEYS}}
    e["install"][platform]["companions"] = list(pin.get("companions") or [])
    return {k: e[k] for k in ENTRY_KEYS}


def load_overlays(directory):
    overlays = [json.loads(p.read_text("utf-8")) for p in sorted(Path(directory).glob("*.json"))]
    overlays.sort(key=lambda o: (o["order"], o["catalog_id"]))
    return overlays


def build(oas, overlays, platform, date):
    plugins = [build_entry(o, oas, platform) for o in overlays if platform in o["install"]]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": date,
        "min_app_version": MIN_APP_VERSION,
        "plugins": plugins,
    }


def render(manifest):
    return json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"


# ---- validator: mirrors src/web_catalog/manifest.rs ---------------------------------------

MAX_ENTRIES, MAX_PATHS, MAX_NAME, MAX_DESCRIPTION, MAX_URL, MAX_PATH, MAX_TEXT = (
    500, 16, 80, 600, 512, 256, 300)
MAX_ARCHIVE_BYTES = 4 * 1024**3
ASSET_HOSTS = ("github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com")
ARCHIVES = ("tar.gz", "tar.xz", "tgz", "zip", "7z", "deb", "none")
INSTALL_KINDS = ("github-release-asset", "deb-asset", "manual-link")
INSTALL_TO = ("ClapDir", "Vst3Dir", "SurgeData")


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
            if k not in obj and k not in ("rolling_tag", "companions"):
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
    if not c.keys("catalogue", data, ["schema_version", "generated_at", "min_app_version", "plugins"]):
        return c.errors
    c.date("generated_at", data["generated_at"])
    if not re.fullmatch(r"\d+\.\d+\.\d+", str(data["min_app_version"])):
        c.fail("min_app_version", "must look like 1.2.3")
    plugins = data["plugins"]
    if not isinstance(plugins, list):
        return c.errors + ["plugins: must be a list"]
    if len(plugins) > MAX_ENTRIES:
        return c.errors + [f"plugins: more than {MAX_ENTRIES} entries"]
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
    if c.keys("license", e["license"], ["spdx", "url"]):
        c.text("license.spdx", e["license"]["spdx"], MAX_TEXT)
        c.https_url("license.url", e["license"]["url"])
    c.https_url("homepage", e["homepage"])
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
    _formats(c, e["formats"], installable)


def _formats(c, f, installable):
    if not c.keys("formats", f, ["clap", "vst3"]):
        return
    clap, vst3 = f["clap"], f["vst3"]
    if clap is not None and c.keys("formats.clap", clap, ["plugin_ids", "features", "paths"]):
        for i in clap["plugin_ids"][:MAX_ENTRIES]:
            c.text("formats.clap.plugin_ids", i, MAX_TEXT)
        for i in clap["features"][:MAX_ENTRIES]:
            c.text("formats.clap.features", i, MAX_NAME)
        c.paths("formats.clap.paths", clap["paths"], ".clap")
    if vst3 is not None and c.keys("formats.vst3", vst3, ["class_ids", "bundles"]):
        for i in vst3["class_ids"][:MAX_ENTRIES]:
            if not (isinstance(i, str) and re.fullmatch(r"[0-9a-fA-F]{32}", i)):
                c.fail("formats.vst3.class_ids", f"{i!r} is not 32 hex digits")
        c.paths("formats.vst3.bundles", vst3["bundles"], ".vst3")
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
    elif i["kind"] in ("github-release-asset", "deb-asset"):
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


# ---- command line -------------------------------------------------------------------------


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--oas", required=True, help="OAS index.json snapshot")
    ap.add_argument("--overlay", required=True, help="directory of overlay/<catalog_id>.json")
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
    text = render(build(oas, overlays, args.platform, date))
    errors = validate(text)
    if errors:
        print("the generated manifest is invalid:", *errors, sep="\n  ", file=sys.stderr)
        return 1
    Path(args.out).write_text(text, "utf-8")
    print(f"wrote {args.out}: {len(overlays)} entries, valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
