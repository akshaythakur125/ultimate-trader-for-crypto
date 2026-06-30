"""Enable kill switch — creates runtime_state/KILL_SWITCH_ON."""

import os
path = os.path.join(os.path.dirname(__file__), "..", "runtime_state", "KILL_SWITCH_ON")
os.makedirs(os.path.dirname(path), exist_ok=True)
with open(path, "w") as f:
    f.write("KILL SWITCH ENGAGED\n")
print(f"[KILL SWITCH ON] {path}")
