"""Disable kill switch — removes runtime_state/KILL_SWITCH_ON."""

import os
path = os.path.join(os.path.dirname(__file__), "..", "runtime_state", "KILL_SWITCH_ON")
if os.path.exists(path):
    os.remove(path)
    print(f"[KILL SWITCH OFF] {path} removed")
else:
    print(f"[KILL SWITCH OFF] no kill switch file at {path}")
