import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from sender import main
from sender import planb_adapter


class RaceWinnerTests(unittest.TestCase):
    def setUp(self):
        self.session = {
            "session_id": "s1", "processing_target": "race", "status": "processing",
            "branches": {"opencap": main._branch_state(), "planb": main._branch_state()},
            "winner": "", "note": "",
        }

        def mutate(session_id, callback):
            self.assertEqual(session_id, "s1")
            callback(self.session)
            return dict(self.session)
        self.mutate = mutate

    def finish(self, branch, success=True):
        result = {"trc_path": f"/{branch}.trc", "mot_path": f"/{branch}.mot", "result_dir": "/results"}
        with patch("sender.main.mutate_session", side_effect=self.mutate):
            main._finish_branch("s1", branch, success, result if success else None, "invalid output")

    def test_first_valid_branch_wins_and_late_branch_is_backup(self):
        self.finish("opencap")
        self.finish("planb")
        self.assertEqual(self.session["winner"], "opencap")
        self.assertEqual(self.session["branches"]["planb"]["status"], "backup")
        self.assertEqual(self.session["winner_results"]["trc_path"], "/opencap.trc")

    def test_planb_can_win_after_opencap_validation_failure(self):
        self.finish("opencap", success=False)
        self.assertEqual(self.session["status"], "processing")
        self.finish("planb")
        self.assertEqual(self.session["winner"], "planb")

    def test_two_failures_mark_session_failed(self):
        self.finish("opencap", success=False)
        self.finish("planb", success=False)
        self.assertEqual(self.session["status"], "failed")

    def test_race_starts_both_workers(self):
        started = []
        def mutate(session_id, callback):
            callback(self.session)
            return dict(self.session)

        class FakeThread:
            def __init__(self, target, args, daemon):
                started.append(target.__name__)
            def start(self):
                pass

        with patch("sender.main.read_sessions", return_value={"sessions": [self.session]}), \
             patch("sender.main.mutate_session", side_effect=mutate), \
             patch("sender.main.threading.Thread", FakeThread):
            main._start_selected_processing("s1")
        self.assertEqual(started, ["_run_opencap_branch", "_run_planb_branch"])

    def test_opencap_only_starts_original_branch_worker(self):
        self.session["processing_target"] = "opencap"
        self.session["branches"] = {"opencap": main._branch_state()}
        started = []
        def mutate(session_id, callback):
            callback(self.session)
            return dict(self.session)
        class FakeThread:
            def __init__(self, target, args, daemon):
                started.append(target.__name__)
            def start(self):
                pass
        with patch("sender.main.read_sessions", return_value={"sessions": [self.session]}), \
             patch("sender.main.mutate_session", side_effect=mutate), \
             patch("sender.main.threading.Thread", FakeThread):
            main._start_selected_processing("s1")
        self.assertEqual(started, ["_run_opencap_branch"])


class UploadTests(unittest.TestCase):
    def test_upload_saves_file_content_with_selected_target(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            records = []
            upload = type("Upload", (), {"filename": "same.mov", "file": BytesIO(b"movie-bytes")})()
            with patch.object(main, "VIDEOS", temp / "videos"), \
                 patch.object(main, "SESSIONS", temp / "sessions"), \
                 patch("sender.main.add_session", side_effect=records.append):
                response = main.upload_video(upload, "race")
            self.assertEqual(response["processing_target"], "race")
            self.assertEqual(len(records), 1)
            self.assertEqual(Path(records[0]["video_path"]).read_bytes(), b"movie-bytes")
            self.assertEqual(set(records[0]["branches"]), {"opencap", "planb"})


class PlanBAdapterTests(unittest.TestCase):
    def test_uses_explicit_paths_and_argument_lists(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            video = temp / "input.mov"
            video.write_bytes(b"video")
            runner = temp / "run_planb.sh"; runner.write_text("#!/bin/bash\n")
            validator = temp / "validate_trc_mot.py"; validator.write_text("# validator\n")
            conda = temp / "conda"; conda.write_text("#!/bin/bash\n")

            class FakeProcess:
                pid = 4242
                returncode = 0
                def communicate(self):
                    output = temp / "task" / "planb_output" / "input"
                    output.mkdir(parents=True)
                    (output / "input.trc").write_text("trc")
                    (output / "input.mot").write_text("mot")
                    return "runner stdout", "runner stderr"

            completed = type("Completed", (), {"returncode": 0, "stdout": "VALIDATION=PASS\n", "stderr": ""})()
            with patch.object(planb_adapter, "PLANB_ROOT", temp), \
                 patch.object(planb_adapter, "PLANB_RUNNER", runner), \
                 patch.object(planb_adapter, "PLANB_VALIDATOR", validator), \
                 patch.object(planb_adapter, "CONDA", conda), \
                 patch("sender.planb_adapter.subprocess.Popen", return_value=FakeProcess()) as popen, \
                 patch("sender.planb_adapter.subprocess.run", return_value=completed) as run:
                result = planb_adapter.run_planb(video, temp / "task")
            self.assertEqual(popen.call_args.args[0], ["bash", str(runner), str(video.resolve())])
            self.assertFalse(popen.call_args.kwargs.get("shell", False))
            self.assertEqual(run.call_args.args[0][-4:], ["--trc", result["trc_path"], "--mot", result["mot_path"]])
            self.assertTrue(Path(result["log_path"]).is_file())


class WinnerFilesTests(unittest.TestCase):
    def test_files_endpoint_returns_only_explicit_winner_pair(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            trc = temp / "winner.trc"; trc.write_text("trc")
            mot = temp / "winner.mot"; mot.write_text("mot")
            session = {"session_id": "s1", "result_dir": str(temp), "winner_results": {"trc_path": str(trc), "mot_path": str(mot)}, "status": "done"}
            with patch("sender.main.read_sessions", return_value={"sessions": [session]}), \
                 patch("sender.main.update_session"):
                result = main.session_files("s1")
            self.assertEqual({item["file_path"] for item in result["files"]}, {str(trc), str(mot)})


if __name__ == "__main__":
    unittest.main()
