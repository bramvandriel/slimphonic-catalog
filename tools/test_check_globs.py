import unittest

from check_globs import glob_match, prefixes


class GlobTests(unittest.TestCase):
    def test_star_stays_inside_one_component(self):
        self.assertTrue(glob_match("*/Surge XT.clap", "pkg/Surge XT.clap"))
        self.assertFalse(glob_match("*/Surge XT.clap", "Surge XT.clap"))
        self.assertFalse(glob_match("*.clap", "a/b.clap"))

    def test_leading_dot_slash_is_ignored(self):
        self.assertTrue(glob_match("Surge XT.clap", "./Surge XT.clap"))

    def test_a_bundle_directory_is_reached_through_its_files(self):
        hits = [r for r in prefixes("Ildaeil.clap/Ildaeil-FX.clap") if glob_match("Ildaeil.clap", r)]
        self.assertEqual(hits, ["Ildaeil.clap"])


if __name__ == "__main__":
    unittest.main()
