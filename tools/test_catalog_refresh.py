"""Run from the repository root: python3 -I -m unittest discover -s tools"""

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
spec = importlib.util.spec_from_file_location("catalog_refresh", HERE / "catalog_refresh.py")
cr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cr)

OAS = json.loads((ROOT / "oas" / "index.json").read_text("utf-8"))
OVERLAYS = cr.load_overlays(ROOT / "overlay")
HIDDEN = cr.load_hidden(ROOT / "hidden.json")
CATEGORIES = cr.load_categories(ROOT / "categories.json")
PROBES = cr.load_probes(ROOT / "probes")


def file(url, system="linux", arch="x64", sha="a" * 64):
    return {"systems": [{"type": system}], "architectures": [arch], "url": url,
            "sha256": sha, "size": 10}


class MappingTests(unittest.TestCase):
    def test_systems_objects_select_the_platform(self):
        v = {"files": [
            file("https://github.com/o/r/releases/download/1/a.zip"),
            file("https://github.com/o/r/releases/download/1/b.zip", arch="arm64"),
            file("https://github.com/o/r/releases/download/1/c.dmg", system="mac"),
            {"systems": [{"type": "linux", "min": 5}, {"type": "win"}], "architectures": ["x64"],
             "url": "https://github.com/o/r/releases/download/1/d.zip"},
        ]}
        urls = [f["url"][-5:] for f in cr.files_for_platform(v, "linux-x86_64")]
        self.assertEqual(urls, ["a.zip", "d.zip"])

    def test_the_five_types_map_to_a_kind(self):
        self.assertEqual(
            {t: cr.kind_of(t) for t in ("instrument", "sampler", "generator", "effect", "tool")},
            {"instrument": "instrument", "sampler": "instrument", "generator": "instrument",
             "effect": "effect", "tool": "effect"})
        self.assertIsNone(cr.kind_of("something-new"))

    def test_every_type_in_the_snapshot_is_mapped(self):
        types = {p["versions"][p["version"]]["type"] for p in OAS["plugins"].values()}
        self.assertTrue(all(cr.kind_of(t) for t in types), types)

    def test_licence_normalisation(self):
        n = cr.normalise_license
        self.assertEqual(n("gpl-3.0"), "GPL-3.0")
        self.assertEqual(n("GPL-3.0"), "GPL-3.0")
        self.assertEqual(n("mit"), "MIT")
        self.assertEqual(n("GPLv3"), "GPL-3.0")
        self.assertEqual(n("agpl-3.0"), "AGPL-3.0")
        self.assertEqual(n("LGPLv2.1"), "LGPL-2.1")
        self.assertIsNone(n("other"))
        self.assertIsNone(n("Custom EULA"))
        self.assertIsNone(n(None))

    def test_every_licence_in_the_snapshot_is_known_or_other(self):
        raw = {p["versions"][p["version"]]["license"] for p in OAS["plugins"].values()}
        self.assertEqual({r for r in raw if not cr.normalise_license(r)}, {"other"})

    def test_a_non_spdx_licence_keeps_the_overlay_value(self):
        oas = {"plugins": {"a/b": {"version": "1", "versions": {"1": {
            "name": "B", "author": "A", "type": "effect", "license": "other",
            "url": "https://github.com/a/b", "description": "d"}}}}}
        overlay = dict(OVERLAYS[0], oas_id="a/b", license={"spdx": "LicenseRef-Custom"})
        e = cr.build_entry(overlay, oas, "linux-x86_64")
        self.assertEqual(e["license"]["spdx"], "LicenseRef-Custom")
        self.assertEqual(e["license"]["url"], e["source"])

    def test_latest_version_is_the_named_one(self):
        pkg = {"version": "1.0", "versions": {"1.0": {"n": 1}, "2.0": {"n": 2}}}
        self.assertEqual(cr.latest_version(pkg), ("1.0", {"n": 1}))

    def test_latest_version_falls_back_to_the_highest_number(self):
        pkg = {"version": "9", "versions": {"1.9.0": {"n": 1}, "1.10.0": {"n": 2}}}
        self.assertEqual(cr.latest_version(pkg)[0], "1.10.0")

    def test_oas_fields_become_the_base_entry(self):
        base = cr.base_entry({"catalog_id": "dexed", "oas_id": "asb2m10/dexed"}, OAS)
        self.assertEqual((base["name"], base["vendor"], base["kind"]),
                         ("Dexed", "Pascal Gauthier", "instrument"))
        self.assertTrue(base["image"]["url"].endswith("/asb2m10/dexed/dexed.jpg"))
        self.assertEqual(base["image"]["sha256"], "")
        self.assertEqual(base["license"]["spdx"], "GPL-3.0")

    def test_overlay_wins_over_oas(self):
        overlay = next(o for o in OVERLAYS if o["catalog_id"] == "dexed")
        e = cr.build_entry(dict(overlay, name="Overridden", description="ours"), OAS, "linux-x86_64")
        self.assertEqual((e["name"], e["description"]), ("Overridden", "ours"))

    def test_long_oas_description_is_trimmed_to_the_limit(self):
        self.assertLessEqual(len(cr.trim_description("word " * 400)), 600)

    def test_rolling_tag_entry_keeps_the_overlay_pin(self):
        overlay = next(o for o in OVERLAYS if o["catalog_id"] == "odin2")
        self.assertTrue(overlay["rolling_tag"])
        pin = overlay["install"]["linux-x86_64"]
        oas = copy.deepcopy(OAS)
        package = oas["plugins"][overlay["oas_id"]]
        _, v = cr.latest_version(package)
        for f in v["files"]:
            if f["url"] == pin["url"]:
                f["sha256"] = "f" * 64  # upstream overwrote the asset
        e = cr.build_entry(overlay, oas, "linux-x86_64")
        self.assertEqual(e["install"]["linux-x86_64"]["sha256"], pin["sha256"])
        notes = cr.drift(overlay, v, "linux-x86_64")
        self.assertEqual(len(notes), 1)
        self.assertIn("rolling tag", notes[0])

    def test_rolling_urls_are_recognised(self):
        self.assertTrue(cr.is_rolling_url("https://github.com/a/b/releases/download/Nightly/x.zip"))
        self.assertFalse(cr.is_rolling_url("https://github.com/a/b/releases/download/v1.0/x.zip"))


class ReproductionTests(unittest.TestCase):
    def test_linux_json_is_reproduced_byte_for_byte(self):
        committed = (ROOT / "linux.json").read_text("utf-8")
        date = json.loads(committed)["generated_at"]
        out = cr.render(cr.build(OAS, OVERLAYS, "linux-x86_64", date, HIDDEN, CATEGORIES, PROBES))
        self.assertEqual(out, committed)

    def test_entries_are_in_overlay_order(self):
        orders = [o["order"] for o in OVERLAYS]
        self.assertEqual(orders, sorted(orders))
        self.assertEqual(len(set(orders)), len(orders))

    def test_main_writes_a_valid_file(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "out.json"
            rc = cr.main(["--oas", str(ROOT / "oas/index.json"), "--overlay", str(ROOT / "overlay"),
                          "--hidden", str(ROOT / "hidden.json"), "--categories",
                          str(ROOT / "categories.json"), "--out", str(out), "--date", "2026-01-02"])
            self.assertEqual(rc, 0)
            self.assertEqual(cr.validate(out.read_text("utf-8")), [])
            self.assertEqual(json.loads(out.read_text("utf-8"))["generated_at"], "2026-01-02")


class OverlayTests(unittest.TestCase):
    def test_every_oas_id_names_an_existing_package(self):
        for o in OVERLAYS:
            if o["oas_id"] is not None:
                self.assertIn(o["oas_id"], OAS["plugins"], o["catalog_id"])

    def test_file_names_match_catalog_ids(self):
        names = sorted(p.stem for p in (ROOT / "overlay").glob("*.json"))
        self.assertEqual(names, sorted(o["catalog_id"] for o in OVERLAYS))


class ValidatorTests(unittest.TestCase):
    def manifest(self):
        return json.loads((ROOT / "linux.json").read_text("utf-8"))

    def errors(self, mutate):
        m = self.manifest()
        mutate(m)
        return cr.validate(json.dumps(m))

    def test_the_committed_file_is_valid(self):
        self.assertEqual(cr.validate((ROOT / "linux.json").read_text("utf-8")), [])

    def test_rejects_http_and_foreign_hosts(self):
        def http(m): m["plugins"][0]["install"]["linux-x86_64"]["url"] = "http://github.com/a/b.zip"
        def host(m): m["plugins"][0]["install"]["linux-x86_64"]["url"] = "https://example.com/a.zip"
        self.assertTrue(self.errors(http))
        self.assertTrue(any("allowed download host" in e for e in self.errors(host)))

    def test_rejects_dotdot_and_absolute_paths(self):
        def dd(m): m["plugins"][1]["formats"]["clap"]["paths"] = ["../Dexed.clap"]
        def ab(m): m["plugins"][1]["formats"]["clap"]["paths"] = ["/Dexed.clap"]
        self.assertTrue(self.errors(dd))
        self.assertTrue(self.errors(ab))

    def test_rejects_bad_sha_size_id_schema_and_too_many_paths(self):
        def sha(m): m["plugins"][0]["install"]["linux-x86_64"]["sha256"] = "ABC"
        def size(m): m["plugins"][0]["install"]["linux-x86_64"]["size_bytes"] = 0
        def ident(m): m["plugins"][0]["catalog_id"] = "Bad_Id"
        def schema(m): m["schema_version"] = 2
        def paths(m): m["plugins"][1]["formats"]["clap"]["paths"] = [f"d{i}.clap" for i in range(17)]
        for mutate in (sha, size, ident, schema, paths):
            self.assertTrue(self.errors(mutate), mutate.__name__)

    def test_rejects_duplicate_ids_and_unknown_fields(self):
        def dup(m): m["plugins"][1]["catalog_id"] = m["plugins"][0]["catalog_id"]
        def extra(m): m["plugins"][0]["surprise"] = 1
        self.assertTrue(any("twice" in e for e in self.errors(dup)))
        self.assertTrue(any("unknown field" in e for e in self.errors(extra)))

    def test_rejects_a_malformed_or_repeated_hidden_key(self):
        def junk(m): m["hidden"][0]["key"] = "ladspa:abc"
        def short(m): m["hidden"][0]["key"] = "vst3:ABCD"
        def dup(m): m["hidden"][1]["key"] = m["hidden"][0]["key"]
        def extra(m): m["hidden"][0]["why"] = "x"
        self.assertTrue(any("is not clap" in e for e in self.errors(junk)))
        self.assertTrue(any("is not clap" in e for e in self.errors(short)))
        self.assertTrue(any("twice" in e for e in self.errors(dup)))
        self.assertTrue(any("unknown field" in e for e in self.errors(extra)))

    def test_the_hidden_list_has_the_editor_plugins(self):
        self.assertEqual(len(self.manifest()["hidden"]), 32)

    def entry(self, m, catalog_id):
        return next(p for p in m["plugins"] if p["catalog_id"] == catalog_id)

    def test_closed_source_has_no_source_and_open_source_needs_one(self):
        m = self.manifest()
        closed = [p["catalog_id"] for p in m["plugins"]
                  if p["license"]["kind"] == "free-closed-source"]
        self.assertEqual(len(closed), 10)
        self.assertTrue(all(self.entry(m, c)["source"] is None for c in closed))
        def with_source(m): self.entry(m, "tal-noisemaker")["source"] = "https://github.com/a/b"
        def without(m): self.entry(m, "surge-xt")["source"] = None
        def bad_kind(m): self.entry(m, "surge-xt")["license"]["kind"] = "shareware"
        def no_kind(m): del self.entry(m, "surge-xt")["license"]["kind"]
        self.assertTrue(any("has none" in e for e in self.errors(with_source)))
        self.assertTrue(any("needs one" in e for e in self.errors(without)))
        self.assertTrue(any("shareware" in e for e in self.errors(bad_kind)))
        self.assertTrue(any("missing field 'kind'" in e for e in self.errors(no_kind)))

    def test_vendor_hosts_are_exact(self):
        def sub(m):
            self.entry(m, "tal-noisemaker")["install"]["linux-x86_64"]["url"] = \
                "https://evil.tal-software.com/x.zip"
        self.assertTrue(any("allowed download host" in e for e in self.errors(sub)))

    def test_data_folder_rules(self):
        def outside(m):
            self.entry(m, "podolski")["formats"]["vst3"]["bundles"] = ["*/Other/Podolski.64.so"]
        def clap_ext(m):
            self.entry(m, "zebralette3")["formats"]["clap"]["paths"] = ["*/Zebralette3/Z.clap"]
        def target(m):
            self.entry(m, "podolski")["install"]["linux-x86_64"]["data"]["install_to"] = "ClapDir"
        def name(m):
            self.entry(m, "podolski")["install"]["linux-x86_64"]["data"]["path"] = "*/.hidden"
        def content(m):
            self.entry(m, "podolski")["content"] = {
                "note": "n", "url": "https://dl.u-he.com/x.tar.xz", "sha256": "a" * 64,
                "size_bytes": 1, "install_to": "UHeData"}
        self.assertTrue(any("not inside the data folder" in e for e in self.errors(outside)))
        self.assertTrue(any("must end with .so" in e for e in self.errors(clap_ext)))
        self.assertTrue(any("only UHeData" in e for e in self.errors(target)))
        self.assertTrue(any("plain folder name" in e for e in self.errors(name)))
        self.assertTrue(any("only for install.data" in e for e in self.errors(content)))
        # An entry without a data folder carries no `data` key.
        self.assertNotIn("data", self.entry(self.manifest(), "surge-xt")["install"]["linux-x86_64"])

    def test_manual_link_rules(self):
        def with_url(m):
            vital = next(p for p in m["plugins"] if p["catalog_id"] == "vital")
            vital["install"]["linux-x86_64"]["url"] = "https://github.com/a/b.zip"
        self.assertTrue(self.errors(with_url))


class CategoryTests(unittest.TestCase):
    def built(self, overlays=None, extra=None, probes=None):
        overlays = OVERLAYS if overlays is None else overlays
        entries = [cr.build_entry(o, OAS, "linux-x86_64") for o in overlays]
        return cr.category_rows(overlays, entries, CATEGORIES if extra is None else extra,
                                PROBES if probes is None else probes)

    def overlay(self, catalog_id):
        return copy.deepcopy(next(o for o in OVERLAYS if o["catalog_id"] == catalog_id))

    def errors(self, overlays=None, extra=None, probes=None):
        with self.assertRaises(cr.CategoryError) as caught:
            self.built(overlays, extra, probes)
        return caught.exception.errors

    def replaced(self, overlay):
        return [overlay if o["catalog_id"] == overlay["catalog_id"] else o for o in OVERLAYS]

    def test_the_committed_data_is_consistent_and_sorted(self):
        rows = self.built()
        self.assertEqual([r["key"] for r in rows], sorted(r["key"] for r in rows))
        self.assertTrue(all(r["category"] in cr.CATEGORY_IDS for r in rows))

    def test_every_bundled_instrument_has_a_row(self):
        keys = {r["key"] for r in self.built()}
        for pid in ("triwave_synth", "luthier", "sampler", "drumkit"):
            self.assertIn(f"clap:com.slimphonic.{pid}", keys)

    def test_maps_are_stripped_from_the_emitted_entries(self):
        for e in json.loads((ROOT / "linux.json").read_text("utf-8"))["plugins"]:
            for block in e["formats"].values():
                self.assertNotIn("categories", block or {}, e["catalog_id"])

    def test_vst3_only_entries_use_class_ids(self):
        rows = {r["key"]: r["category"] for r in self.built()}
        self.assertEqual(rows["vst3:e2cc953290e863f06405e13924e34b24"], "drums")

    def test_rejects_an_unknown_category(self):
        o = self.overlay("dexed")
        o["formats"]["clap"]["categories"]["com.digital-suburban.dexed"] = "chiptune"
        self.assertTrue(any("unknown category" in e for e in self.errors(self.replaced(o))))
        bad = CATEGORIES + [{"key": "clap:x.y", "name": "X", "category": "nope"}]
        self.assertTrue(any("unknown category" in e for e in self.errors(extra=bad)))

    def test_rejects_an_uncovered_instrument_id(self):
        o = self.overlay("dexed")
        del o["formats"]["clap"]["categories"]
        self.assertTrue(any("has no category" in e for e in self.errors(self.replaced(o))))

    def test_rejects_an_uncovered_probed_instrument_of_a_both_entry(self):
        o = self.overlay("dpf-plugins")
        del o["formats"]["clap"]["categories"]["studio.kx.distrho.Nekobi"]
        errors = self.errors(self.replaced(o))
        self.assertTrue(any("Nekobi" in e and "has no category" in e for e in errors))

    def test_a_both_entry_needs_its_probe(self):
        probes = {k: v for k, v in PROBES.items() if k != "plugdata"}
        self.assertTrue(any("probes/plugdata.json" in e for e in self.errors(probes=probes)))

    def test_rejects_a_map_key_not_among_the_formats_ids(self):
        o = self.overlay("dexed")
        o["formats"]["clap"]["categories"]["com.example.other"] = "fm"
        self.assertTrue(any("is not one of its plugin_ids" in e
                            for e in self.errors(self.replaced(o))))

    def test_rejects_a_duplicate_key(self):
        dup = CATEGORIES + [{"key": "clap:com.digital-suburban.dexed", "name": "D",
                             "category": "fm"}]
        self.assertTrue(any("two category rows" in e for e in self.errors(extra=dup)))

    def test_vitalium_is_exempt_until_it_has_ids(self):
        self.assertIn("vitalium", cr.COVERAGE_EXEMPT)
        self.built()  # no row, no error

    def test_validator_rejects_bad_category_rows(self):
        m = json.loads((ROOT / "linux.json").read_text("utf-8"))

        def errors(mutate):
            mm = copy.deepcopy(m)
            mutate(mm)
            return cr.validate(json.dumps(mm))

        def key(mm): mm["categories"][0]["key"] = "vst3:XYZ"
        def cat(mm): mm["categories"][0]["category"] = "chiptune"
        def dup(mm): mm["categories"][1]["key"] = mm["categories"][0]["key"]
        def extra(mm): mm["categories"][0]["why"] = "x"
        self.assertTrue(any("is not clap" in e for e in errors(key)))
        self.assertTrue(any("not a known category" in e for e in errors(cat)))
        self.assertTrue(any("twice" in e for e in errors(dup)))
        self.assertTrue(any("unknown field" in e for e in errors(extra)))


if __name__ == "__main__":
    unittest.main()
