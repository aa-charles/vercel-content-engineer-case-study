"""Model constants for the agent pipeline.

Centralized so version bumps and model swaps happen in one place rather than
in each agent file. Each agent imports its specific model name.
"""

EXTRACT_MODEL = "claude-sonnet-4-6"  # extraction layer; Sonnet for structured per-source extraction
COMPARE_MODEL = "claude-opus-4-7"    # synthesis layer; Opus per project convention
DRAFT_MODEL   = "claude-opus-4-7"    # drafting layer; Opus for the writerly pass
