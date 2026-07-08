"""Pytest configuration."""

import os
import sys
from pathlib import Path

# Project root on path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Isolated vault for tests
os.environ.setdefault("HIVE_HOME", str(ROOT / ".hive-test"))
os.environ.setdefault("HIVE_VAULT_MASTER_PASSWORD", "test-master-password-12345")
