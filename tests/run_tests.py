"""File entry point also supports coverage with the embedded Python distribution."""

import unittest
from pathlib import Path

suite = unittest.defaultTestLoader.discover(str(Path(__file__).parent), pattern="test_*.py")
raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful())
