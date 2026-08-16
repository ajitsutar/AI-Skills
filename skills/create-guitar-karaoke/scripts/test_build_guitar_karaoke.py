#!/usr/bin/env python3
"""Fast synthetic tests for build_guitar_karaoke.py (no model download)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import soundfile as sf

import build_guitar_karaoke as guitar


class TimestampAndMaskTests(unittest.TestCase):
    def test_timestamp_formats_and_merging(self) -> None:
        self.assertEqual(guitar.parse_timestamp("01:02.5"), 62.5)
        self.assertEqual(guitar.parse_timestamp("1:01:02"), 3662.0)
        windows = guitar.parse_windows(["2-5", "4-7", "9-end"], 1000, 100)
        self.assertEqual(windows, [(200, 700), (900, 1000)])

    def test_window_and_inverse_envelopes_are_complements(self) -> None:
        base = {
            "frames": 1000,
            "sample_rate": 100,
            "fade_seconds": 0.1,
            "windows": [{"start_frame": 200, "end_frame": 500}],
        }
        windowed = guitar.make_scope_envelope(np, {**base, "scope": "windows"})
        outside = guitar.make_scope_envelope(np, {**base, "scope": "outside-windows"})
        np.testing.assert_allclose(windowed + outside, 1.0, atol=1e-7)
        self.assertEqual(float(windowed[0]), 0.0)
        self.assertEqual(float(windowed[250]), 1.0)
        self.assertEqual(float(outside[250]), 0.0)

    def test_whole_scope_is_fully_active(self) -> None:
        manifest = {
            "frames": 100,
            "sample_rate": 100,
            "fade_seconds": 0.1,
            "scope": "whole",
            "windows": [],
        }
        np.testing.assert_array_equal(guitar.make_scope_envelope(np, manifest), 1.0)


class StemTests(unittest.TestCase):
    def test_external_offset_gain_and_strict_zero_offset_length(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stem = np.linspace(-0.2, 0.2, 100, dtype="float32")[:, None]
            stem = np.repeat(stem, 2, axis=1)
            stem_path = root / "stem.wav"
            sf.write(stem_path, stem, 100, subtype="FLOAT")
            manifest = {
                "frames": 200,
                "sample_rate": 100,
                "stem_source": "external",
                "external_stem_source": str(stem_path),
                "external_stem_source_sha256": guitar.hash_file(stem_path),
                "external_stem_wav": str(stem_path),
                "external_stem_wav_sha256": guitar.hash_file(stem_path),
                "external_stem_offset_seconds": 0.5,
                "external_stem_gain": -1.0,
            }
            aligned = guitar.load_estimate(manifest)
            np.testing.assert_allclose(aligned[:50], 0.0)
            np.testing.assert_allclose(aligned[50:150], -stem, atol=1e-6)

            manifest["external_stem_offset_seconds"] = 0.0
            with self.assertRaises(SystemExit):
                guitar.load_estimate(manifest)

            manifest["external_stem_offset_seconds"] = 0.5
            stem_path.write_bytes(b"tampered")
            with self.assertRaises(SystemExit):
                guitar.load_estimate(manifest)

    def test_multi_tile_blend_restores_scale(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stems = root / "stems"
            stems.mkdir()
            guitar_signal = np.sin(np.arange(200, dtype="float32") * 0.1)[:, None] * 0.2
            guitar_signal = np.repeat(guitar_signal, 2, axis=1)
            tiles = [
                {
                    "clip_wav": str(root / "tile_a.wav"),
                    "clip_start_frame": 0,
                    "clip_source_frames": 120,
                    "clip_written_frames": 120,
                    "core_start_frame": 0,
                    "core_end_frame": 100,
                    "input_scale": 0.5,
                },
                {
                    "clip_wav": str(root / "tile_b.wav"),
                    "clip_start_frame": 80,
                    "clip_source_frames": 120,
                    "clip_written_frames": 120,
                    "core_start_frame": 100,
                    "core_end_frame": 200,
                    "input_scale": 0.5,
                },
            ]
            for tile in tiles:
                clip = np.zeros((tile["clip_source_frames"], 2), dtype="float32")
                sf.write(tile["clip_wav"], clip, 100, subtype="FLOAT")
                tile["clip_sha256"] = guitar.hash_file(Path(tile["clip_wav"]))
            manifest = {
                "frames": 200,
                "sample_rate": 100,
                "stem_source": guitar.MODEL_LABEL,
                "stems_dir": str(stems),
                "scope": "whole",
                "fade_seconds": 0.0,
                "windows": [],
                "tiles": tiles,
            }
            for tile in tiles:
                start = tile["clip_start_frame"]
                count = tile["clip_source_frames"]
                sf.write(
                    guitar.expected_guitar_stem(manifest, tile),
                    guitar_signal[start : start + count] * 0.5,
                    100,
                    subtype="FLOAT",
                )
                stem_path = guitar.expected_guitar_stem(manifest, tile)
                attestation = guitar.attestation_core(tile, "model", "config", "0.44.5")
                attestation["stem_sha256"] = guitar.hash_file(stem_path)
                guitar.attestation_path(stem_path).write_text(
                    json.dumps(attestation), encoding="utf-8"
                )
            with mock.patch.object(
                guitar,
                "verify_manifest_model_assets",
                return_value=("model", "config", "0.44.5"),
            ):
                restored = guitar.load_estimate(manifest)
            np.testing.assert_allclose(restored, guitar_signal, atol=2e-6)


class SafetyAndCacheTests(unittest.TestCase):
    def test_parser_accepts_all_stem_kinds_and_scopes(self) -> None:
        parser = guitar.build_parser()
        for stem_kind in ("aggregate-guitar", "lead-guitar", "rhythm-guitar", "custom"):
            for scope in ("whole", "windows", "outside-windows"):
                arguments = [
                    "song.wav",
                    "--scope",
                    scope,
                    "--stem-kind",
                    stem_kind,
                    "--work-dir",
                    "work",
                ]
                if scope != "whole":
                    arguments.extend(["--window", "1-2"])
                parsed = parser.parse_args(arguments)
                self.assertEqual(parsed.stem_kind, stem_kind)
                self.assertEqual(parsed.scope, scope)

    def test_manifest_schema_is_gated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "manifest.json").write_text(
                json.dumps({"schema_version": guitar.MANIFEST_SCHEMA_VERSION - 1}),
                encoding="utf-8",
            )
            with self.assertRaises(SystemExit):
                guitar.load_manifest(root)

    def test_manifest_generated_paths_are_bound_to_work_dir(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            work = root / "work"
            clips = work / "clips"
            stems = work / "stems"
            clips.mkdir(parents=True)
            stems.mkdir()
            clip = clips / "tile.wav"
            clip.write_bytes(b"clip")
            manifest = {
                "schema_version": guitar.MANIFEST_SCHEMA_VERSION,
                "source": str(root / "source.wav"),
                "source_sha256": "0" * 64,
                "work_dir": str(work),
                "master_wav": str(work / "master.wav"),
                "master_wav_sha256": "1" * 64,
                "sample_rate": 44_100,
                "frames": 100,
                "scope": "whole",
                "stem_kind": "aggregate-guitar",
                "stem_source": guitar.MODEL_LABEL,
                "fade_seconds": 0.35,
                "models_dir": str(work / "models"),
                "stems_dir": str(stems),
                "windows": [],
                "tiles": [{
                    "clip_wav": str(clip),
                    "clip_start_frame": 0,
                    "clip_source_frames": 100,
                    "clip_written_frames": 100,
                    "core_start_frame": 0,
                    "core_end_frame": 100,
                    "input_scale": 1.0,
                    "clip_sha256": guitar.hash_file(clip),
                }],
            }
            (work / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            self.assertEqual(guitar.load_manifest(work)["work_dir"], str(work))

            manifest["work_dir"] = str(root / "elsewhere")
            (work / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(SystemExit):
                guitar.load_manifest(work)

    def test_output_cannot_replace_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.wav"
            source.write_bytes(b"source")
            args = argparse.Namespace(
                input=source,
                work_dir=root / "work",
                model_dir=None,
                image=None,
                stem_file=None,
                output=source,
                report=None,
                video_output=None,
                overwrite=False,
            )
            with self.assertRaises(SystemExit):
                guitar.validate_paths(args, will_mix=True)

    def test_attested_cache_detects_stem_change(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            clip = root / "clip.wav"
            stem = root / "stem.wav"
            clip.write_bytes(b"clip")
            stem.write_bytes(b"stem")
            tile = {"clip_wav": str(clip), "clip_sha256": guitar.hash_file(clip)}
            attestation = guitar.attestation_core(tile, "model", "config", "0.44.5")
            attestation["stem_sha256"] = guitar.hash_file(stem)
            guitar.attestation_path(stem).write_text(json.dumps(attestation), encoding="utf-8")
            self.assertTrue(guitar.cache_is_valid(tile, stem, "model", "config", "0.44.5"))
            stem.write_bytes(b"changed")
            self.assertFalse(guitar.cache_is_valid(tile, stem, "model", "config", "0.44.5"))

            stem.write_bytes(b"stem")
            attestation["settings"]["use_soundfile"] = False
            guitar.attestation_path(stem).write_text(json.dumps(attestation), encoding="utf-8")
            self.assertFalse(guitar.cache_is_valid(tile, stem, "model", "config", "0.44.5"))

            attestation = guitar.attestation_core(tile, "model", "config", "0.44.5")
            attestation["stem_sha256"] = guitar.hash_file(stem)
            guitar.attestation_path(stem).write_text(json.dumps(attestation), encoding="utf-8")
            clip.write_bytes(b"changed clip")
            with self.assertRaises(SystemExit):
                guitar.cache_is_valid(tile, stem, "model", "config", "0.44.5")

    def test_external_stem_source_must_remain_attested(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "source-stem.wav"
            decoded_path = root / "decoded-stem.wav"
            stem = np.zeros((100, 2), dtype="float32")
            sf.write(source_path, stem, 100, subtype="FLOAT")
            sf.write(decoded_path, stem, 100, subtype="FLOAT")
            manifest = {
                "frames": 100,
                "sample_rate": 100,
                "stem_source": "external",
                "external_stem_source": str(source_path),
                "external_stem_source_sha256": guitar.hash_file(source_path),
                "external_stem_wav": str(decoded_path),
                "external_stem_wav_sha256": guitar.hash_file(decoded_path),
                "external_stem_offset_seconds": 0.0,
                "external_stem_gain": 1.0,
            }
            source_path.unlink()
            with self.assertRaises(SystemExit):
                guitar.load_estimate(manifest)

    def test_invalid_model_cache_is_removed_before_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stems = root / "stems"
            stems.mkdir()
            tile = {"clip_wav": str(root / "clip.wav")}
            manifest = {"stems_dir": str(stems), "tiles": [tile]}
            stem = guitar.expected_guitar_stem(manifest, tile)
            sidecar = guitar.attestation_path(stem)
            stem.write_bytes(b"stale stem")
            sidecar.write_text("{}", encoding="utf-8")
            unrelated = stems / "unrelated.wav"
            unrelated.write_bytes(b"keep")

            guitar.clear_invalid_model_cache(manifest, [tile])

            self.assertFalse(stem.exists())
            self.assertFalse(sidecar.exists())
            self.assertTrue(unrelated.exists())

    def test_generated_model_stem_format_is_verified(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            stem = Path(directory) / "stem.wav"
            sf.write(stem, np.zeros((128, 2), dtype="float32"), 44_100, subtype="FLOAT")
            guitar.validate_model_stem_file(stem, {"clip_written_frames": 128})
            with self.assertRaises(SystemExit):
                guitar.validate_model_stem_file(stem, {"clip_written_frames": 127})

    def test_sha256_fields_cannot_be_blank(self) -> None:
        with self.assertRaises(SystemExit):
            guitar.require_sha256("", "test hash")
        self.assertEqual(guitar.require_sha256("A" * 64, "test hash"), "a" * 64)

    def test_nonaggregate_label_requires_external_stem(self) -> None:
        script = Path(guitar.__file__).resolve()
        completed = subprocess.run(
            [
                sys.executable,
                str(script),
                "missing.wav",
                "--scope",
                "whole",
                "--stem-kind",
                "rhythm-guitar",
                "--work-dir",
                "work",
                "--output",
                "output.wav",
            ],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("require --stem-file", completed.stderr)


if __name__ == "__main__":
    unittest.main()
