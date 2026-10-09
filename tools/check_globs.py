#!/usr/bin/env python3
"""Checks every overlay entry's globs against the real archive it pins.

    python3 -I tools/check_globs.py --overlay overlay/ --archives DIR [DIR ...]

For each entry with a downloadable archive found (by file name from the pinned url) in one of
the --archives directories, this lists the archive with the system tar/unzip/7z/ar and asserts
that every plugin glob (and companion glob) matches at least one member, mirroring the app's
`glob_match` (a glob names a whole path, `*` stays within one component, a leading `./` is
ignored; a plugin glob may name a directory, i.e. a bundle, whose contents come along), that
the file's size and sha256 equal the pin, and warns when the archive exceeds the app's member
cap. Entries whose archive is not on disk are skipped with a note. Exit status 1 on any miss.
Only the listings are read; nothing is extracted or run.
"""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

MAX_MEMBERS = 10_000  # src/web_catalog/tools.rs MAX_LIST_ENTRIES
PLUGIN_EXTS = (".clap", ".vst3", ".so")


def component_match(pattern, text):
    p, t = pattern, text
    pi = ti = 0
    star = None
    while ti < len(t):
        if pi < len(p) and p[pi] == "*":
            star = (pi, ti)
            pi += 1
        elif pi < len(p) and p[pi] == t[ti]:
            pi += 1
            ti += 1
        elif star:
            pi, ti = star[0] + 1, star[1] + 1
            star = (star[0], star[1] + 1)
        else:
            return False
    return all(c == "*" for c in p[pi:])


def glob_match(pattern, path):
    def strip(s):
        while s.startswith("./"):
            s = s[2:]
        return s

    pat, parts = strip(pattern).split("/"), strip(path).split("/")
    return (len(pat) == len(parts) and all(c not in ("", "..") for c in parts)
            and all(component_match(a, b) for a, b in zip(pat, parts)))


def prefixes(path):
    parts = path.strip("/").split("/")
    return ["/".join(parts[: i + 1]) for i in range(len(parts))]


def run(argv, **kw):
    return subprocess.run(argv, check=True, capture_output=True, **kw).stdout


def list_members(path, kind):
    """Member paths of the archive (the inner data archive for a deb)."""
    if kind == "zip":
        out = run(["unzip", "-Z1", "--", str(path)], text=True, errors="replace")
        return [m for m in out.splitlines() if m]
    if kind in ("tar.gz", "tar.xz", "tgz"):
        out = run(["tar", "-tf", str(path)], text=True, errors="replace")
        return [m for m in out.splitlines() if m]
    if kind == "7z":
        out = run(["7z", "l", "-slt", "-ba", str(path)], text=True, errors="replace")
        return [line[7:] for line in out.splitlines() if line.startswith("Path = ")]
    if kind == "deb":
        names = run(["ar", "t", str(path)], text=True).split()
        inner = next(n for n in names if n.startswith("data.tar"))
        data = run(["ar", "p", str(path), inner])
        flag = {".xz": "-J", ".zst": "--zstd", ".gz": "-z"}.get(Path(inner).suffix, "-")
        argv = ["tar", "-tf", "-"] if flag == "-" else ["tar", flag, "-tf", "-"]
        out = subprocess.run(argv, input=data, check=True, capture_output=True).stdout
        return [m for m in out.decode(errors="replace").splitlines() if m]
    raise ValueError(f"unknown archive kind {kind}")


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def plugin_globs(entry):
    fmts = entry["formats"]
    out = []
    if fmts.get("clap"):
        out += fmts["clap"]["paths"]
    if fmts.get("vst3"):
        out += fmts["vst3"]["bundles"]
    return out


def check_entry(entry, pin, archive_path):
    """Returns the list of problems for one entry."""
    problems = []
    if archive_path.stat().st_size != pin["size_bytes"]:
        problems.append(f"size {archive_path.stat().st_size} != pinned {pin['size_bytes']}")
    if sha256_of(archive_path) != pin["sha256"]:
        problems.append("sha256 differs from the pin")
    members = list_members(archive_path, pin["archive"])
    if len(members) >= MAX_MEMBERS:  # an app limit, not a catalogue error: reported, not failed
        print(f"WARN   {len(members)} members: the app refuses archives of {MAX_MEMBERS}+")
    for g in plugin_globs(entry):
        hits = [r for m in members for r in prefixes(m) if glob_match(g, r)]
        if not hits:
            problems.append(f"plugin glob {g!r} matches nothing")
        elif not all(h.rsplit("/", 1)[-1].endswith(PLUGIN_EXTS) for h in hits):
            problems.append(f"plugin glob {g!r} hits a path not named like a plugin")
    for g in pin.get("companions") or []:
        if not any(glob_match(g, m) for m in members):
            problems.append(f"companion glob {g!r} matches nothing")
    return problems


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--overlay", required=True)
    ap.add_argument("--archives", nargs="+", required=True, help="directories holding the downloaded archives")
    ap.add_argument("--platform", default="linux-x86_64")
    args = ap.parse_args(argv)
    bad = checked = 0
    for f in sorted(Path(args.overlay).glob("*.json")):
        o = json.loads(f.read_text("utf-8"))
        pin = o["install"].get(args.platform)
        if not pin or not pin.get("url"):
            print(f"skip   {o['catalog_id']}: no downloadable archive")
            continue
        name = pin["url"].rsplit("/", 1)[-1]
        found = next((Path(d) / name for d in args.archives if (Path(d) / name).is_file()), None)
        if found is None:  # a release asset saved under another name: match on the pinned size
            found = next((q for d in args.archives for q in Path(d).glob("*")
                          if q.is_file() and q.stat().st_size == pin["size_bytes"]), None)
        if found is None:
            print(f"skip   {o['catalog_id']}: {name} not on disk")
            continue
        entry = {"formats": o["formats"]}
        problems = check_entry(entry, pin, found)
        checked += 1
        if problems:
            bad += 1
            for p in problems:
                print(f"FAIL   {o['catalog_id']}: {p}")
        else:
            print(f"ok     {o['catalog_id']}")
    print(f"{checked} archives checked, {bad} with problems")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
