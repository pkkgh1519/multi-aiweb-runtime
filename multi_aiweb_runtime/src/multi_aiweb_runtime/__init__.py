"""Compatibility-facing package alias for Multi-AI Web Runtime.

The implementation currently lives in :mod:`chatgpt_web_runtime` to preserve
backward compatibility for existing imports and stored artifacts.
"""

from chatgpt_web_runtime import *  # noqa: F401,F403
