"""Notification ownership: daemon observes; the displaying host acknowledges."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from company.runtime.loop import Runtime
from company.runtime.models import GoalHandler
from company.runtime.notifications import deliver_pending, pending_notifications


class _Owner(GoalHandler):
    id = "notification_owner"


class NotificationDeliveryTests(unittest.TestCase):
    def test_unseen_notification_survives_daemon_observation(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Runtime(Path(tmp) / "state.sqlite", {"notification_owner": _Owner()})
            goal = runtime.create_goal(
                name="Keep attention visible", owner_id="notification_owner",
                metric="done", operator="eq", target=True, config={})
            cycle = runtime.store.cycle(goal["id"])
            note = runtime.store.notify(
                goal["id"], cycle["id"], "action_required",
                {"required_user_action": "Review this blocker"})

            self.assertEqual(1, deliver_pending(runtime.store))
            self.assertEqual([note["id"]], [row["id"] for row in pending_notifications(runtime.store)])

            deliver_pending(runtime.store, surfaced_ids=[note["id"]])
            self.assertEqual([], pending_notifications(runtime.store))


if __name__ == "__main__":
    unittest.main()
