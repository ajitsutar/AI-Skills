import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parent


def load_script(name):
    path = SCRIPT_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


render = load_script("render_karaoke_video")
separate = load_script("separate_vocals")


class KaraokeRendererTests(unittest.TestCase):
    def test_help_does_not_require_pillow(self):
        result = subprocess.run(
            [sys.executable, "-B", str(SCRIPT_DIR / "render_karaoke_video.py"), "--help"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--overwrite", result.stdout)

    def test_authoritative_lyrics_replace_timing_text(self):
        rows = [{"start": 1.0, "end": 2.0, "text": "Timing transcript"}]
        merged = render.apply_authoritative_lyrics(rows, ["User lyric"], allow_mismatch=True)
        self.assertEqual(merged[0]["text"], "User lyric")
        with self.assertRaises(SystemExit):
            render.apply_authoritative_lyrics(rows, ["User lyric"], allow_mismatch=False)

    def test_timing_completion_never_forces_overlap(self):
        rows = render.complete_ends(
            [
                {"start": 1.0, "end": None, "text": "one"},
                {"start": 1.2, "end": 1.8, "text": "two"},
            ],
            3.0,
        )
        self.assertLess(rows[0]["end"], rows[1]["start"])
        with self.assertRaises(SystemExit):
            render.complete_ends(
                [
                    {"start": 1.0, "end": 1.5, "text": "one"},
                    {"start": 1.2, "end": 1.8, "text": "two"},
                ],
                3.0,
            )

    def test_ass_time_rolls_over_at_59_59_999(self):
        self.assertEqual(render.ass_time(3599.999), "1:00:00.00")

    def test_srt_and_ass_are_supported(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            srt = root / "timing.srt"
            srt.write_text("1\n00:00:01,000 --> 00:00:02,500\nHello\n", encoding="utf-8")
            self.assertEqual(render.load_timings(srt)[0]["text"], "Hello")

            ass = root / "timing.ass"
            ass.write_text(
                "[Events]\nFormat: Layer, Start, End, Style, Text\n"
                "Dialogue: 0,0:00:01.00,0:00:02.50,Default,{\\i1}Hello\n",
                encoding="utf-8",
            )
            self.assertEqual(render.load_timings(ass)[0]["text"], "Hello")

    def test_ass_filter_uses_safe_relative_name_under_apostrophe_parent(self):
        with tempfile.TemporaryDirectory(prefix="Guns N' Roses ") as temporary:
            root = Path(temporary)
            audio = root / "audio.wav"
            background = root / "background.png"
            captions = root / "captions.ass"
            output = root / "video.mp4"
            for path in (audio, background, captions):
                path.write_bytes(b"x")

            captured = {}

            def fake_run(command, check, cwd):
                captured["command"] = command
                captured["cwd"] = cwd
                Path(command[-1]).write_bytes(b"video")

            with mock.patch.object(render.subprocess, "run", side_effect=fake_run):
                render.render("ffmpeg", audio, background, captions, output, 2.0)

            filter_value = captured["command"][captured["command"].index("-vf") + 1]
            self.assertEqual(filter_value, "ass=filename=captions.ass")
            self.assertEqual(Path(captured["cwd"]).resolve(), root.resolve())
            self.assertNotIn("Guns N' Roses", filter_value)

    def test_output_collision_and_overwrite_gate(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            audio = root / "song.mp3"
            lyrics = root / "lyrics.txt"
            audio.write_bytes(b"audio")
            lyrics.write_text("line", encoding="utf-8")
            with self.assertRaises(SystemExit):
                render.validate_paths(audio, lyrics, None, audio, False)
            output = root / "video.mp4"
            output.write_bytes(b"existing")
            with self.assertRaises(SystemExit):
                render.validate_paths(audio, lyrics, None, output, False)
            resolved, _ = render.validate_paths(audio, lyrics, None, output, True)
            self.assertEqual(resolved, output.resolve())

    def test_render_verification_checks_streams_duration_and_decode(self):
        metadata = json.dumps(
            {
                "format": {"duration": "120.10"},
                "streams": [{"codec_type": "video"}, {"codec_type": "audio"}],
            }
        )
        responses = [
            subprocess.CompletedProcess([], 0, stdout=metadata, stderr=""),
            subprocess.CompletedProcess([], 0, stdout="", stderr=""),
        ]
        with mock.patch.object(render.subprocess, "run", side_effect=responses) as run:
            render.verify_rendered_output("ffmpeg", "video.mp4", 120.0, "ffprobe")
        self.assertEqual(run.call_count, 2)
        self.assertIn("format=duration:stream=codec_type", run.call_args_list[0].args[0])
        self.assertIn("null", run.call_args_list[1].args[0])

    def test_late_output_collision_is_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            staged_video = root / "staged.mp4"
            staged_ass = root / "staged.ass"
            output = root / "video.mp4"
            ass_output = root / "video.ass"
            staged_video.write_bytes(b"new video")
            staged_ass.write_bytes(b"new ass")
            output.write_bytes(b"late existing video")

            with self.assertRaisesRegex(SystemExit, "created during rendering"):
                render.publish_rendered_pair(staged_video, output, staged_ass, ass_output)

            self.assertEqual(output.read_bytes(), b"late existing video")
            self.assertFalse(ass_output.exists())

    def test_pair_publication_rolls_back_when_second_link_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            staged_video = root / "staged.mp4"
            staged_ass = root / "staged.ass"
            output = root / "video.mp4"
            ass_output = root / "video.ass"
            staged_video.write_bytes(b"new video")
            staged_ass.write_bytes(b"new ass")
            real_link = render.os.link
            calls = 0

            def fail_second_link(source, destination):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("simulated second-link failure")
                return real_link(source, destination)

            with mock.patch.object(render.os, "link", side_effect=fail_second_link):
                with self.assertRaisesRegex(SystemExit, "simulated second-link failure"):
                    render.publish_rendered_pair(staged_video, output, staged_ass, ass_output)

            self.assertFalse(output.exists())
            self.assertFalse(ass_output.exists())
            self.assertEqual(staged_video.read_bytes(), b"new video")
            self.assertEqual(staged_ass.read_bytes(), b"new ass")

    def test_overwrite_pair_is_consistent_and_failure_restores_old_pair(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "video.mp4"
            ass_output = root / "video.ass"
            output.write_bytes(b"old video")
            ass_output.write_bytes(b"old ass")

            staged_video = root / "new.mp4"
            staged_ass = root / "new.ass"
            staged_video.write_bytes(b"new video")
            staged_ass.write_bytes(b"new ass")
            render.publish_rendered_pair(staged_video, output, staged_ass, ass_output, overwrite=True)
            self.assertEqual(output.read_bytes(), b"new video")
            self.assertEqual(ass_output.read_bytes(), b"new ass")

            failed_video = root / "failed.mp4"
            failed_ass = root / "failed.ass"
            failed_video.write_bytes(b"failed video")
            failed_ass.write_bytes(b"failed ass")
            real_link = render.os.link
            calls = 0

            def fail_second_link(source, destination):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("simulated overwrite failure")
                return real_link(source, destination)

            with mock.patch.object(render.os, "link", side_effect=fail_second_link):
                with self.assertRaisesRegex(SystemExit, "simulated overwrite failure"):
                    render.publish_rendered_pair(failed_video, output, failed_ass, ass_output, overwrite=True)

            self.assertEqual(output.read_bytes(), b"new video")
            self.assertEqual(ass_output.read_bytes(), b"new ass")


class VocalSeparationTests(unittest.TestCase):
    def test_find_stem_is_scoped_to_isolated_job(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stale = root / "shared" / "htdemucs" / "other" / "no_vocals.wav"
            stale.parent.mkdir(parents=True)
            stale.write_bytes(b"stale")
            job = root / "job"
            generated = job / "htdemucs" / "song" / "no_vocals.wav"
            generated.parent.mkdir(parents=True)
            generated.write_bytes(b"new")
            self.assertEqual(separate.find_no_vocals(job, "htdemucs", "song.mp3"), generated)

    def test_missing_demucs_detection_is_actionable(self):
        with mock.patch.object(separate.importlib.util, "find_spec", return_value=None):
            with self.assertRaisesRegex(SystemExit, "Demucs is not installed"):
                separate.ensure_demucs_available()

    def test_publish_track_atomically_moves_generated_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            job = root / "job"
            source_dir = job / "htdemucs" / "song"
            source_dir.mkdir(parents=True)
            stem = source_dir / "no_vocals.wav"
            stem.write_bytes(b"new")
            (source_dir / "vocals.wav").write_bytes(b"voice")
            destination = root / "published"
            published = separate.publish_track(job, stem, destination)
            self.assertEqual(published.read_bytes(), b"new")
            self.assertEqual((published.parent / "vocals.wav").read_bytes(), b"voice")

    def test_publish_track_preserves_existing_directory_by_default(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            job = root / "job"
            source_dir = job / "htdemucs" / "song"
            source_dir.mkdir(parents=True)
            stem = source_dir / "no_vocals.wav"
            stem.write_bytes(b"new")
            destination_root = root / "published"
            existing = destination_root / "htdemucs" / "song"
            existing.mkdir(parents=True)
            (existing / "no_vocals.wav").write_bytes(b"old")

            with self.assertRaisesRegex(SystemExit, "Refusing to overwrite"):
                separate.publish_track(job, stem, destination_root)

            self.assertEqual((existing / "no_vocals.wav").read_bytes(), b"old")
            self.assertEqual(stem.read_bytes(), b"new")

    def test_publish_track_overwrite_replaces_the_complete_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            job = root / "job"
            source_dir = job / "htdemucs" / "song"
            source_dir.mkdir(parents=True)
            stem = source_dir / "no_vocals.wav"
            stem.write_bytes(b"new")
            (source_dir / "vocals.wav").write_bytes(b"new voice")
            destination_root = root / "published"
            existing = destination_root / "htdemucs" / "song"
            existing.mkdir(parents=True)
            (existing / "no_vocals.wav").write_bytes(b"old")
            (existing / "obsolete.wav").write_bytes(b"obsolete")

            published = separate.publish_track(job, stem, destination_root, overwrite=True)

            self.assertEqual(published.read_bytes(), b"new")
            self.assertEqual((published.parent / "vocals.wav").read_bytes(), b"new voice")
            self.assertFalse((published.parent / "obsolete.wav").exists())

    def test_publish_track_failure_restores_the_prior_complete_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            job = root / "job"
            source_dir = job / "htdemucs" / "song"
            source_dir.mkdir(parents=True)
            stem = source_dir / "no_vocals.wav"
            stem.write_bytes(b"new")
            (source_dir / "vocals.wav").write_bytes(b"new voice")
            destination_root = root / "published"
            existing = destination_root / "htdemucs" / "song"
            existing.mkdir(parents=True)
            (existing / "no_vocals.wav").write_bytes(b"old")
            (existing / "old-only.wav").write_bytes(b"old only")
            real_link = separate.os.link
            calls = 0

            def fail_second_link(source, destination):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("simulated track publication failure")
                return real_link(source, destination)

            with mock.patch.object(separate.os, "link", side_effect=fail_second_link):
                with self.assertRaisesRegex(SystemExit, "simulated track publication failure"):
                    separate.publish_track(job, stem, destination_root, overwrite=True)

            self.assertEqual((existing / "no_vocals.wav").read_bytes(), b"old")
            self.assertEqual((existing / "old-only.wav").read_bytes(), b"old only")
            self.assertFalse((existing / "vocals.wav").exists())

    def test_publish_track_never_replaces_a_directory_containing_input(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            job = root / "job"
            source_dir = job / "htdemucs" / "song"
            source_dir.mkdir(parents=True)
            stem = source_dir / "no_vocals.wav"
            stem.write_bytes(b"new")
            destination_root = root / "published"
            input_audio = destination_root / "htdemucs" / "song" / "source.mp3"
            input_audio.parent.mkdir(parents=True)
            input_audio.write_bytes(b"source")

            with self.assertRaisesRegex(SystemExit, "contains the source audio"):
                separate.publish_track(job, stem, destination_root, overwrite=True, input_audio=input_audio)

            self.assertEqual(input_audio.read_bytes(), b"source")


if __name__ == "__main__":
    unittest.main()
