"""
Pytest configuration for review queue tests.

Sets up the Python path to allow importing from the symphony-bridge module.
"""

import sys
from pathlib import Path

# Add the symphony-bridge/src directory to the path
# We use a special approach since the directory has a hyphen
symphony_src = Path(__file__).parent.parent
sys.path.insert(0, str(symphony_src))

# Also add the project root for shared imports
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))
