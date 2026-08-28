"""
Root-level pytest configuration for the Stock Analysis Agent backend tests.

Adds the ``backend/`` directory to ``sys.path`` so ``app.*`` imports resolve
without needing to install the package.
"""

import sys
import os

# Ensure ``backend/`` is on the path when pytest is run from the repo root
# or from within the ``backend/`` directory itself.
sys.path.insert(0, os.path.dirname(__file__))
