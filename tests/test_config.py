"""Installations and runtime reloads preserve the same user configuration."""
import unittest
import support  # isolate paths before importing runtime configuration

from dynamicisland.config import complete_settings


class ConfigurationTests(unittest.TestCase):
    def test_upgrade_preserves_user_values_and_removes_ineffective_controls(self):
        settings = complete_settings({"compactMinWidth": 140, "sources": [{"type": "rss"}],
                                      "customFlag": True, "stackDepth": 3})
        self.assertEqual(settings["compactMinWidth"], 140)
        self.assertEqual(settings["sources"], [{"type": "rss"}])
        self.assertTrue(settings["customFlag"])
        self.assertNotIn("stackDepth", settings)
        self.assertFalse(settings["showJobs"])

    def test_mutable_defaults_do_not_leak_between_configurations(self):
        settings = complete_settings({})
        settings["sources"].append({"type": "rss"})
        self.assertEqual(complete_settings({})["sources"], [])
