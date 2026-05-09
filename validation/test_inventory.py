#!/usr/bin/env python3
"""Tests for ``tools/inventory_user_blueprints.py`` and the
``tools/blueprint_classifier.py`` helper.

Stdlib-only. Run with::

    python3 -m unittest validation.test_inventory

The tests run the inventory CLI against the user's actual
``library/external/factorioprints/`` and ``library/external/factorio_school/``
fixtures (which were committed by the scrapers agent) plus the binary
``~/.factorio/blueprint-storage-2.dat`` if present, and assert structural
shape on the manifest + digest.
"""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import blueprint_codec  # noqa: E402
import blueprint_classifier  # noqa: E402
import inventory_user_blueprints as inv  # noqa: E402


# ---------------------------------------------------------------------------
# Classifier unit tests
# ---------------------------------------------------------------------------


class ClassifierUnitTests(unittest.TestCase):
    """Tiny blueprint corner cases for ``blueprint_classifier.classify``."""

    def test_self_test_pole(self):
        # Use the canonical 1-electric-pole blueprint that ships with
        # tools/blueprint_codec.py's self-test.
        decoded = blueprint_codec.decode(blueprint_codec._KNOWN_STRING)
        cls = blueprint_classifier.classify(decoded)
        # 1-entity pole should produce a meaningful, non-empty label.
        self.assertTrue(cls.label, f"empty label for 1-entity pole: {cls!r}")
        self.assertIn(cls.confidence, ("high", "medium", "low"))
        # The label should mention either 'pole' or 'single entity'.
        low = cls.label.lower()
        self.assertTrue(
            "pole" in low or "single" in low,
            f"expected pole/single in label, got {cls.label!r}",
        )

    def test_empty_blueprint(self):
        decoded = {"blueprint": {"item": "blueprint", "version": 0,
                                 "icons": [], "entities": []}}
        cls = blueprint_classifier.classify(decoded)
        self.assertIn("empty", cls.label.lower())

    def test_smelter_array_classification(self):
        # Hand-craft an 8-furnace blueprint to exercise the smelter rule.
        ents = [
            {"entity_number": i + 1, "name": "stone-furnace",
             "position": {"x": float(i * 2), "y": 0.0}}
            for i in range(8)
        ]
        decoded = {"blueprint": {
            "item": "blueprint", "version": 0,
            "icons": [{"signal": {"name": "stone-furnace"}, "index": 1}],
            "entities": ents,
        }}
        cls = blueprint_classifier.classify(decoded)
        self.assertIn("smelter", cls.label.lower())
        self.assertEqual(cls.confidence, "high")

    def test_solar_farm_classification(self):
        # 4 solar panels + 1 accumulator triggers the solar farm rule.
        ents: list[dict] = []
        eid = 1
        for i in range(4):
            ents.append({"entity_number": eid, "name": "solar-panel",
                         "position": {"x": float(i * 3), "y": 0.0}})
            eid += 1
        ents.append({"entity_number": eid, "name": "accumulator",
                     "position": {"x": 0.0, "y": 4.0}})
        decoded = {"blueprint": {"item": "blueprint", "version": 0,
                                 "icons": [], "entities": ents}}
        cls = blueprint_classifier.classify(decoded)
        self.assertIn("solar", cls.label.lower())


# ---------------------------------------------------------------------------
# End-to-end inventory tests
# ---------------------------------------------------------------------------


EXTERNAL_ROOT = ROOT / "library" / "external"


@unittest.skipUnless(
    (EXTERNAL_ROOT / "factorioprints").is_dir()
    and (EXTERNAL_ROOT / "factorio_school").is_dir(),
    "library/external scraper fixtures not present",
)
class InventoryEndToEndTests(unittest.TestCase):
    """Run the inventory CLI against the user's actual external fixtures."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.manifest = pathlib.Path(cls.tmp.name) / "inv.json"
        cls.digest = pathlib.Path(cls.tmp.name) / "inv.md"
        # Skip the binary .dat (we test that path in a separate test below)
        # and skip the empty personal library to keep this hermetic.
        rc = inv.main([
            "--no-dat",
            "--include-external",
            "--external", str(EXTERNAL_ROOT),
            "--personal", str(pathlib.Path(cls.tmp.name) / "empty-personal"),
            "--manifest", str(cls.manifest),
            "--out", str(cls.digest),
        ])
        cls.rc = rc

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_exit_code(self):
        self.assertEqual(self.rc, 0)

    def test_manifest_parses(self):
        data = json.loads(self.manifest.read_text(encoding="utf-8"))
        self.assertIn("records", data)
        self.assertGreaterEqual(len(data["records"]), 2,
                                f"expected >= 2 records, got {len(data['records'])}")
        self.assertIn("source_counts", data)
        self.assertIn("generated_at", data)

    def test_record_schema(self):
        data = json.loads(self.manifest.read_text(encoding="utf-8"))
        required_fields = {
            "id", "source", "label", "kind", "string_size_bytes",
            "decoded", "purpose_guess", "purpose_confidence",
            "purpose_reasons", "mod_compat", "unknown_entities",
            "throughput_estimate", "validation_questions", "notes",
        }
        for rec in data["records"]:
            missing = required_fields - rec.keys()
            self.assertFalse(
                missing,
                f"record {rec.get('id')!r} missing fields: {missing}",
            )
            mc_required = {"required_mods", "enabled", "disabled",
                           "missing", "zip_only", "substitutes_available"}
            self.assertTrue(
                mc_required.issubset(rec["mod_compat"].keys()),
                f"record {rec['id']} mod_compat missing keys: "
                f"{mc_required - rec['mod_compat'].keys()}",
            )

    def test_each_record_has_section_header(self):
        digest = self.digest.read_text(encoding="utf-8")
        data = json.loads(self.manifest.read_text(encoding="utf-8"))
        for rec in data["records"]:
            header = f"### {rec['id']}"
            self.assertIn(
                header, digest,
                f"digest missing section header for {rec['id']}",
            )

    def test_each_record_has_questions(self):
        data = json.loads(self.manifest.read_text(encoding="utf-8"))
        for rec in data["records"]:
            self.assertGreaterEqual(
                len(rec["validation_questions"]), 1,
                f"record {rec['id']} has no validation questions",
            )

    def test_legacy_rename_detected_in_factoriobin_demo(self):
        """The committed factoriobin demo blueprint references 1.x logistic
        chest names (`logistic-chest-passive-provider` etc.). Confirm we
        flag those as `legacy_renamed` with a modern equivalent."""
        data = json.loads(self.manifest.read_text(encoding="utf-8"))
        seen_legacy = False
        for rec in data["records"]:
            for u in rec["unknown_entities"]:
                if u["status"] == "legacy_renamed":
                    seen_legacy = True
                    self.assertIsNotNone(u["suggested_name"])
                    self.assertNotEqual(u["name"], u["suggested_name"])
        self.assertTrue(
            seen_legacy,
            "expected at least one legacy_renamed entity in the external "
            "fixtures (factoriobin demo carries 1.x chest names)",
        )


# ---------------------------------------------------------------------------
# Optional: real .dat sanity test (only if the user has a .dat file)
# ---------------------------------------------------------------------------


REAL_DAT = pathlib.Path.home() / ".factorio" / "blueprint-storage-2.dat"


@unittest.skipUnless(REAL_DAT.exists(),
                     f"{REAL_DAT} not present; skipping .dat sanity test")
class DatInventoryTests(unittest.TestCase):
    """If the user has a real blueprint-storage-2.dat, the inventory should
    surface the envelope-only records without crashing."""

    def test_inventory_reads_dat(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = pathlib.Path(tmp) / "inv.json"
            digest = pathlib.Path(tmp) / "inv.md"
            rc = inv.main([
                "--dat", str(REAL_DAT),
                "--external", str(EXTERNAL_ROOT),
                "--personal", str(pathlib.Path(tmp) / "empty-personal"),
                "--manifest", str(manifest),
                "--out", str(digest),
            ])
            self.assertEqual(rc, 0)
            data = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertGreaterEqual(data["source_counts"]["dat"], 1)
            # Every dat-sourced record should be envelope-only
            # (the parser doesn't decode bodies yet).
            dat_records = [r for r in data["records"]
                           if r["source"].startswith(str(REAL_DAT))]
            self.assertTrue(dat_records, "no dat records were recorded")
            for r in dat_records:
                self.assertEqual(r["kind"], "envelope-only",
                                 f"dat record {r['id']} should be envelope-only "
                                 f"but kind={r['kind']!r}")


if __name__ == "__main__":
    unittest.main()
