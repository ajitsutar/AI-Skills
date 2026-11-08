#!/usr/bin/env python3
"""Fast stdlib-only tests for the optional SAM Audio adapter."""

from __future__ import annotations

import contextlib
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import separate_prompted_audio as sam


class TimestampAndSafetyTests(unittest.TestCase):
    def test_timestamps_and_official_anchor_shape(self) -> None:
        self.assertEqual(sam.parse_timestamp("01:02.5"), 62.5)
        self.assertEqual(
            sam.build_anchors([["2", "3.5"], ["8", "9"]], [["0", "1"]], 10.0),
            [["-", 0.0, 1.0], ["+", 2.0, 3.5], ["+", 8.0, 9.0]],
        )

    def test_span_validation(self) -> None:
        with self.assertRaisesRegex(sam.UserError, "positive-span"):
            sam.build_anchors([], [["0", "1"]], 10.0)
        with self.assertRaisesRegex(sam.UserError, "overlap"):
            sam.build_anchors([["1", "3"]], [["2", "4"]], 10.0)
        with self.assertRaisesRegex(sam.UserError, "exceeds"):
            sam.build_anchors([["9", "11"]], [], 10.0)

    def test_frame_fit_allows_rounding_but_rejects_material_duration_loss(self) -> None:
        adjustment, tolerance = sam.validate_frame_adjustment(47_999, 48_000, 48_000)
        self.assertEqual(adjustment, 1)
        self.assertEqual(tolerance, 480)
        with self.assertRaisesRegex(sam.UserError, "materially different duration"):
            sam.validate_frame_adjustment(47_000, 48_000, 48_000)

    def test_safe_outputs_and_no_source_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.wav"
            source.write_bytes(b"audio")
            outputs = sam.plan_outputs(source, root / "out", "../unsafe:name")
            self.assertTrue(all(path.parent == root / "out" for path in outputs.values()))
            self.assertFalse(any("/" in path.name or ":" in path.name for path in outputs.values()))
            outputs["target"] = source
            with self.assertRaisesRegex(sam.UserError, "source audio"):
                sam.validate_output_paths(source, outputs, True)


class FakeBatch:
    def to(self, device):
        self.device = device
        return self


class FakeModel:
    load_calls = []
    separate_calls = []

    @classmethod
    def from_pretrained(cls, model_id, **kwargs):
        cls.load_calls.append((model_id, kwargs))
        return cls()

    def eval(self):
        return self

    def to(self, device):
        return self

    def separate(self, batch, **kwargs):
        self.separate_calls.append(kwargs)
        return SimpleNamespace(target="target", residual="residual")


class FakeProcessor:
    load_calls = []
    process_calls = []
    audio_sampling_rate = 48_000

    @classmethod
    def from_pretrained(cls, model_id, **kwargs):
        cls.load_calls.append((model_id, kwargs))
        return cls()

    def __call__(self, **kwargs):
        self.process_calls.append(kwargs)
        return FakeBatch()


class OfficialApiTests(unittest.TestCase):
    def setUp(self) -> None:
        FakeModel.load_calls.clear()
        FakeModel.separate_calls.clear()
        FakeProcessor.load_calls.clear()
        FakeProcessor.process_calls.clear()
        self.runtime = SimpleNamespace(
            SAMAudio=FakeModel, SAMAudioProcessor=FakeProcessor,
            torch=SimpleNamespace(inference_mode=contextlib.nullcontext),
        )

    def test_text_prompt_uses_documented_api(self) -> None:
        _, rate, loaded = sam.run_official_api(
            self.runtime, "facebook/sam-audio-large", Path("clip.wav"),
            "lead electric guitar", [], "cuda:0", False, True, 8, revision="revision",
        )
        self.assertEqual(rate, 48_000)
        self.assertEqual(loaded["revision"], "revision")
        self.assertEqual(FakeModel.load_calls[-1], (
            "facebook/sam-audio-large", {"revision": "revision"}
        ))
        self.assertEqual(FakeProcessor.load_calls[-1], FakeModel.load_calls[-1])
        self.assertEqual(FakeProcessor.process_calls[-1], {
            "audios": ["clip.wav"], "descriptions": ["lead electric guitar"]
        })
        self.assertEqual(FakeModel.separate_calls[-1], {
            "predict_spans": True, "reranking_candidates": 8
        })

    def test_span_prompt_nests_anchors_once(self) -> None:
        anchors = [["+", 2.0, 3.0], ["-", 0.0, 1.0]]
        _, _, loaded = sam.run_official_api(
            self.runtime, "facebook/sam-audio-large", Path("clip.wav"),
            "lead electric guitar", anchors, "cpu", True, False, 1,
            local_snapshot="C:/cache/sam-snapshot",
        )
        self.assertEqual(loaded["from_pretrained_source"], "C:/cache/sam-snapshot")
        self.assertTrue(loaded["local_files_only"])
        self.assertEqual(FakeModel.load_calls[-1], (
            "C:/cache/sam-snapshot", {"local_files_only": True}
        ))
        self.assertEqual(FakeProcessor.load_calls[-1], FakeModel.load_calls[-1])
        self.assertEqual(FakeProcessor.process_calls[-1]["anchors"], [anchors])
        self.assertEqual(FakeModel.separate_calls[-1], {})


class PreflightAndCommitTests(unittest.TestCase):
    def test_cuda_request_has_actionable_error(self) -> None:
        torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False))
        with self.assertRaisesRegex(sam.UserError, "CUDA was requested"):
            sam.resolve_device(torch, "cuda")

    def test_remote_access_heads_config_and_weight_with_implicit_auth(self) -> None:
        calls = []
        class Api:
            def model_info(self, repo_id, token):
                self.token = token
                return SimpleNamespace(sha="revision", siblings=[
                    SimpleNamespace(rfilename="config.json"),
                    SimpleNamespace(rfilename="checkpoint.pt"),
                ])
        hub = SimpleNamespace(
            HfApi=lambda: Api(),
            hf_hub_url=lambda repo_id, filename, revision: f"https://example/{revision}/{filename}",
            get_hf_file_metadata=lambda url, token: calls.append((url, token)) or SimpleNamespace(size=10),
        )
        result = sam.check_model_access(hub, "facebook/sam-audio-large", False)
        self.assertEqual(result["status"], "authenticated-artifact-heads-accessible")
        self.assertEqual(calls, [
            ("https://example/revision/config.json", True),
            ("https://example/revision/checkpoint.pt", True),
        ])

    def test_inaccessible_model_error_redacts_auth(self) -> None:
        synthetic_credential = "hf_" + "abcdefghijklmnop"
        class Api:
            def model_info(self, repo_id, token):
                raise RuntimeError("Bearer " + synthetic_credential)
        with self.assertRaises(sam.UserError) as raised:
            sam.check_model_access(SimpleNamespace(HfApi=lambda: Api()), "model", False)
        self.assertNotIn(synthetic_credential, str(raised.exception))

    def test_overwrite_preserves_backup_if_restore_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            staged = {}
            for name in ("target", "residual"):
                final, temporary = root / name, root / f".{name}.tmp"
                final.write_text("old", encoding="utf-8")
                temporary.write_text("new", encoding="utf-8")
                staged[final] = temporary
            real_replace = os.replace
            state = {"install_count": 0, "restore_failed": False}
            def flaky_replace(source, destination):
                source, destination = Path(source), Path(destination)
                if source in staged.values():
                    state["install_count"] += 1
                    if state["install_count"] == 2:
                        raise OSError("install failed")
                if source.suffix == ".backup" and not state["restore_failed"]:
                    state["restore_failed"] = True
                    raise OSError("restore failed")
                return real_replace(source, destination)
            with mock.patch.object(sam.os, "replace", side_effect=flaky_replace):
                with self.assertRaisesRegex(sam.UserError, "backups were preserved") as raised:
                    sam.commit_bundle(staged, True)
            self.assertIn("preserved backup", str(raised.exception))
            self.assertTrue(any(root.glob(".sam-audio-*.backup")))

    def test_bundle_lock_blocks_concurrent_writer_and_directory_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            final, temporary = root / "target", root / ".target.tmp"
            temporary.write_text("new", encoding="utf-8")
            staged = {final: temporary}
            lock = sam.bundle_lock_path(list(staged))
            lock.write_text("busy", encoding="utf-8")
            with self.assertRaisesRegex(sam.UserError, "Another process"):
                sam.commit_bundle(staged, False)
            lock.unlink()
            final.mkdir()
            with self.assertRaisesRegex(sam.UserError, "non-file"):
                sam.commit_bundle(staged, True)
            self.assertFalse(lock.exists())

    def test_stereo_source_rejects_mono_outputs(self) -> None:
        mono = SimpleNamespace(shape=(1, 48_000))
        with self.assertRaisesRegex(sam.UserError, "not eligible for subtraction"):
            sam.validate_output_channels(2, mono, mono)
        sam.validate_output_channels(1, mono, mono)

    def test_help_is_lazy_and_exposes_preflight(self) -> None:
        script = Path(sam.__file__).resolve()
        with tempfile.TemporaryDirectory() as directory:
            blocker = Path(directory)
            for name in ("torch", "torchaudio", "soundfile", "sam_audio", "huggingface_hub"):
                (blocker / f"{name}.py").write_text("raise RuntimeError('imported')\n", encoding="utf-8")
            environment = os.environ.copy()
            environment["PYTHONPATH"] = str(blocker)
            completed = subprocess.run(
                [sys.executable, str(script), "--help"], capture_output=True, text=True, env=environment
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("--preflight", completed.stdout)


if __name__ == "__main__":
    unittest.main()
