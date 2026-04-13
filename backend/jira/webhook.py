# This module has been renamed to pipeline.py.
# This shim re-exports everything from pipeline.py for backward compatibility,
# including names that start with _ (not exported by 'import *' by default).
import jira.pipeline as _pipeline  # noqa: E402
globals().update(
    {k: v for k, v in vars(_pipeline).items() if not (k.startswith("__") and k.endswith("__"))}
)
