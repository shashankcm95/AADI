"""Shared test configuration for the users service."""
import sys
import os

# Add shared layer to path first (simulates Lambda Layer at runtime)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../shared/python')))
# Add src/ to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

# Avoid cross-service module collisions when running full-repo pytest.
# POS integration uses a single handlers.py file that conflicts with users' handlers/ package.
_MODULES_TO_CLEAR = [k for k in sys.modules if k in (
    'app', 'utils', 'handlers', 'db', 'models', 'engine', 'errors', 'logger',
    'auth', 'pos_mapper',
) or k.startswith('handlers.')]
for _m in _MODULES_TO_CLEAR:
    sys.modules.pop(_m, None)
