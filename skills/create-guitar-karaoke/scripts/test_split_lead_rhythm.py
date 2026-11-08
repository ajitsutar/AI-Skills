#!/usr/bin/env python3
"""Focused tests for the experimental lead/rhythm helper; no model download."""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import split_lead_rhythm as splitter

try:
    import numpy as np
    import soundfile as sf
except ImportError:
    np = None
    sf = None


def rights_record(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "checkpoint_sha256": splitter.MODEL_SHA256,
                "config_sha256": splitter.CONFIG_SHA256,
                "rights_holder": "Synthetic unit-test fixture",
                "license_name": "Synthetic test grant",
                "terms_source": "Unit-test fixture only",
                "permitted_use": "Mock inference tests",
                "reviewed_by": "Unit test",
                "covers_model_weights": True,
                "covers_config": True,
                "intended_use_permitted": True,
            }
        ),
        encoding="utf-8",
    )
    return path


class PreflightTests(unittest.TestCase):
    def test_bundled_config_is_pinned(self) -> None:
        config, digest = splitter.validate_config()
        self.assertEqual(digest, splitter.CONFIG_SHA256)
        self.assertEqual(config["sample_rate"], 44_100)
        self.assertTrue(config["stereo"])
        self.assertEqual(config["num_stems"], 1)

    def test_experimental_acknowledgement_never_replaces_rights_record(self) -> None:
        args = argparse.Namespace(
            experimental=True,
            acknowledge_role_bleed=True,
            model_license_evidence=None,
        )
        with self.assertRaisesRegex(SystemExit, "does not establish model rights"):
            splitter.require_experimental_acknowledgement(args)

    def test_rights_record_must_cover_exact_assets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = rights_record(Path(directory) / "rights.json")
            _, evidence, digest = splitter.read_rights_evidence(path)
            self.assertEqual(evidence["checkpoint_sha256"], splitter.MODEL_SHA256)
            self.assertEqual(len(digest), 64)
            evidence["covers_model_weights"] = False
            path.write_text(json.dumps(evidence), encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "covers_model_weights"):
                splitter.read_rights_evidence(path)

            evidence["covers_model_weights"] = True
            evidence["license_name"] = "unverified"
            path.write_text(json.dumps(evidence), encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "verified 'license_name'"):
                splitter.read_rights_evidence(path)

    def test_wrong_checkpoint_hash_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "wrong.ckpt"
            checkpoint.write_bytes(b"not the pinned model")
            with self.assertRaisesRegex(SystemExit, "hash mismatch"):
                splitter.validate_checkpoint(checkpoint)

    def test_cli_refuses_before_inputs_without_experimental_gate(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "split_lead_rhythm.py"),
                "missing.wav",
                "--checkpoint",
                "missing.ckpt",
                "--output-dir",
                "out",
            ],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("--experimental", completed.stderr)


class SafeLoadTests(unittest.TestCase):
    def test_checkpoint_load_is_weights_only_and_state_dict_is_strict(self) -> None:
        class FakeTorch:
            def __init__(self) -> None:
                self.load_call = None

            def set_num_threads(self, value):
                self.threads = value

            def manual_seed(self, value):
                self.seed = value

            def load(self, path, **kwargs):
                self.load_call = (path, kwargs)
                return {"weight": "fixture"}

        class FakeModel:
            def __init__(self, **config):
                self.config = config

            def load_state_dict(self, state, strict):
                self.state_call = (state, strict)

            def eval(self):
                self.evaluated = True

        fake_torch = FakeTorch()
        model = splitter.load_model(
            Path("model.ckpt"),
            {"dim": 1},
            3,
            torch_module=fake_torch,
            model_class=FakeModel,
        )
        self.assertEqual(fake_torch.threads, 3)
        self.assertEqual(fake_torch.load_call[1], {"map_location": "cpu", "weights_only": True})
        self.assertEqual(model.state_call, ({"weight": "fixture"}, True))
        self.assertTrue(model.evaluated)


class PublicationTests(unittest.TestCase):
    def test_failed_overwrite_restores_outputs_from_external_backups(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stage = root / "stage"
            stage.mkdir()
            destinations = [root / name for name in ("lead.wav", "rhythm.wav", "report.json")]
            sources = [stage / name for name in ("lead.wav", "rhythm.wav", "report.json")]
            for index, destination in enumerate(destinations):
                destination.write_bytes(f"old-{index}".encode())
            for index, source in enumerate(sources):
                source.write_bytes(f"new-{index}".encode())
            real_link = splitter.os.link
            calls = 0

            def fail_second_link(source, destination):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("synthetic publication failure")
                return real_link(source, destination)

            with mock.patch.object(splitter.os, "link", side_effect=fail_second_link):
                with self.assertRaisesRegex(SystemExit, "synthetic publication failure"):
                    splitter.publish_stage(
                        dict(zip(destinations, sources)),
                        overwrite=True,
                        lock_path=root / ".publish.lock",
                    )
            for index, destination in enumerate(destinations):
                self.assertEqual(destination.read_bytes(), f"old-{index}".encode())
            self.assertEqual(list(root.glob("*.bak")), [])


@unittest.skipUnless(np is not None and sf is not None, "NumPy and SoundFile required")
class SyntheticPipelineTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec("torch"), "Optional torch runtime required")
    def test_overlap_add_identity_short_and_long(self) -> None:
        import torch
        torch.set_num_threads(1)
        for frames in (1, 7, 23, 100):
            with self.subTest(frames=frames):
                mix = np.linspace(-0.2, 0.2, frames * 2, dtype="float32").reshape(frames, 2)
                lead = splitter.infer_lead(
                    mix, lambda batch: batch, np, torch,
                    chunk_frames=16, step_frames=8, fade_frames=4, show_progress=False,
                )
                np.testing.assert_allclose(lead, mix, atol=1e-7, rtol=0)

    def test_mock_inference_publishes_exact_duration_and_residual(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "aggregate.wav"
            checkpoint = root / "model.ckpt"
            checkpoint.write_bytes(b"synthetic checkpoint")
            evidence_path = rights_record(root / "rights.json")
            mix = np.linspace(-0.25, 0.25, 257, dtype="float32")[:, None]
            mix = np.repeat(mix, 2, axis=1)
            sf.write(source, mix, 44_100, subtype="FLOAT")
            lead = mix * np.float32(0.4)
            args = argparse.Namespace(
                input=source,
                checkpoint=checkpoint,
                model_license_evidence=evidence_path,
                output_dir=root / "out",
                threads=2,
                experimental=True,
                acknowledge_role_bleed=True,
                overwrite=False,
            )
            with mock.patch.object(
                splitter,
                "validate_checkpoint",
                return_value=(checkpoint.resolve(), splitter.MODEL_SHA256),
            ), mock.patch.object(
                splitter,
                "load_runtime",
                return_value=(np, sf, object(), object()),
            ), mock.patch.object(splitter, "load_model", return_value=object()), mock.patch.object(
                splitter, "infer_lead", return_value=lead
            ):
                lead_path, rhythm_path, report_path = splitter.run_split(args)
            actual_lead, rate = sf.read(lead_path, dtype="float32", always_2d=True)
            actual_rhythm, _ = sf.read(rhythm_path, dtype="float32", always_2d=True)
            self.assertEqual(rate, 44_100)
            self.assertEqual(len(actual_lead), len(mix))
            np.testing.assert_allclose(actual_lead, lead, atol=0)
            np.testing.assert_allclose(actual_lead + actual_rhythm, mix, atol=1e-7)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["input"]["frames"], len(mix))
            self.assertEqual(report["inference"]["rhythm_definition"], "aggregate_guitar_minus_lead")
            self.assertEqual(report["model"]["upstream_public_provenance_status"], "unverified")
            self.assertEqual(set(report["rights_evidence"]), {"schema_version", "sha256"})
            self.assertNotIn("Unit-test fixture only", report_path.read_text())


if __name__ == "__main__":
    unittest.main()
