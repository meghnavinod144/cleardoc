"""Test configuration — runs BEFORE any test imports the app.

Points the app at a throwaway database so tests never touch dev data
and always start clean. (conftest.py is pytest's magic filename for
shared setup.)
"""

import os
import tempfile
from pathlib import Path

_test_db = Path(tempfile.mkdtemp()) / "test.db"
os.environ["CLEARDOC_DATABASE_URL"] = f"sqlite:///{_test_db}"
