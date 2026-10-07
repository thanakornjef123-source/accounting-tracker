"""UI tests write to a throwaway database, never to data/tracker.db."""

import os
import tempfile
from pathlib import Path

os.environ["TRACKER_DB"] = str(Path(tempfile.mkdtemp(prefix="tracker-ui-")) / "ui.db")
