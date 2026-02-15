"""
Shared test configuration for the orders service.

Adds the src/ directory to sys.path so tests can import modules
without the sys.path.append hack in every test file.
"""
import sys
import os

# Add src/ to path once for all test files
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

# Avoid cross-service module collisions when running full-repo pytest.
for module_name in ("app", "db", "engine", "models", "handlers"):
    sys.modules.pop(module_name, None)
