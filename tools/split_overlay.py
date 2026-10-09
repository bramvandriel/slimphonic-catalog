#!/usr/bin/env python3
"""One-off: how overlay/ was born. Splits a hand-written linux.json into one overlay file per
entry, keeping only what Open Audio Stack cannot provide (or provides differently), so that
catalog_refresh.py rebuilds the entry.

    python3 -I tools/split_overlay.py --oas oas/index.json --manifest linux.json --out overlay/

The OAS package of an entry is found by its image URL slug (the `oas_id`); an entry whose
image is not in OAS has `oas_id: null`. Re-running it on an already-refreshed linux.json is
harmless but pointless: edit the overlay files instead.
"""

import argparse
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("catalog_refresh", HERE / "catalog_refresh.py")
refresh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(refresh)

# Surge XT's package is "surge", not "surge-xt" (its image url in the hand-written file was a
# guess); two other picks are not in OAS at all.
OAS_ID_OVERRIDE = {"surge-xt": "surge-synthesizer/surge"}


def find_oas_id(entry, oas):
    if entry["catalog_id"] in OAS_ID_OVERRIDE:
        return OAS_ID_OVERRIDE[entry["catalog_id"]]
    url = (entry.get("image") or {}).get("url", "")
    if "/plugins/" in url:
        slug = url.split("/plugins/", 1)[1].rsplit("/", 1)[0]
        if slug in oas["plugins"]:
            return slug
    return None


def split(entry, order, oas, platform):
    oas_id = find_oas_id(entry, oas)
    o = {
        "catalog_id": entry["catalog_id"],
        "order": order,
        "oas_id": oas_id,
        "editors_pick": entry["score"]["editors_pick"],
        "score_note": entry["score"]["note"],
        "tested_with": entry["score"]["tested_with"],
        "description": entry["description"],
        "experimental": entry["experimental"],
        "rolling_tag": entry["rolling_tag"],
    }
    # Everything else is stored only where OAS (or the rule that follows the entry's source)
    # would not reproduce it.
    base = refresh.base_entry({"catalog_id": entry["catalog_id"], "oas_id": oas_id}, oas)
    for key in ("name", "vendor", "kind", "homepage", "source"):
        if base.get(key) != entry[key]:
            o[key] = entry[key]
    # OAS's own image wins when the entry has a package (this corrects the guessed Surge XT url).
    if oas_id is None:
        o["image"] = entry["image"]
    source = o.get("source", base.get("source"))
    if base.get("license", {}).get("spdx") != entry["license"]["spdx"]:
        o["license"] = {"spdx": entry["license"]["spdx"]}
    if entry["license"]["url"] != source:
        o.setdefault("license", {})["url"] = entry["license"]["url"]
    o["github"] = entry["github"]
    o["formats"] = entry["formats"]
    o["content"] = entry["content"]
    o["install"] = entry["install"]
    return o


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--oas", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--platform", default=refresh.DEFAULT_PLATFORM)
    args = ap.parse_args()
    oas = json.loads(Path(args.oas).read_text("utf-8"))
    manifest = json.loads(Path(args.manifest).read_text("utf-8"))
    out = Path(args.out)
    out.mkdir(exist_ok=True)
    for order, entry in enumerate(manifest["plugins"]):
        o = split(entry, order, oas, args.platform)
        (out / f"{entry['catalog_id']}.json").write_text(
            json.dumps(o, indent=2, ensure_ascii=False) + "\n", "utf-8")
        print(entry["catalog_id"], "oas_id =", o["oas_id"])


if __name__ == "__main__":
    main()
