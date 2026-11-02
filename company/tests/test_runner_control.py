"""The retired runner cannot launch processes or alter unrelated schedules."""
import json,tempfile,unittest
from pathlib import Path
from company.runtime.service import RunnerService,automation_enabled
from company.commands.goal_runtime import CleanCommandRuntime


class RetiredRunnerContract(unittest.TestCase):
    def test_no_start_enable_or_watch_can_run_a_product_daemon(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);database=root/'company.sqlite'
            service=RunnerService(root,database)
            for operation in (service.start,service.enable):
                with self.assertRaisesRegex(RuntimeError,'retired'):operation()
            self.assertFalse(automation_enabled(root))
            runtime=CleanCommandRuntime(database)
            with self.assertRaisesRegex(RuntimeError,'retired'):runtime.watch()
            self.assertFalse((root/'runner.pid').exists())
            self.assertFalse((root/'automation.json').exists())

    def test_reading_old_runner_metadata_does_not_signal_or_remove_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);service=RunnerService(root,root/'company.sqlite')
            metadata={'pid':123456,'command':['some-unrelated-owner-process']}
            service.pid_path.write_text(json.dumps(metadata))
            before=service.pid_path.read_bytes()
            self.assertEqual(service.status()['recorded_process'],metadata)
            with self.assertRaisesRegex(RuntimeError,'explicitly'):service.stop()
            self.assertEqual(service.pid_path.read_bytes(),before)
