"""gimbal.prism.server — FastAPI web configurator (split for clarity).

Submodules:
  - app: FastAPI app + lifespan + middleware + static mount + HTML index
  - routes: HTTP + WebSocket route handlers (APIRouter)
  - conversions: DraftIn -> ScenarioDraft conversion helper
  - wire: Pydantic wire forms (ExportIn; DraftIn/UserIn re-exported from state)
"""
from gimbal.prism.server.app import app, STATIC_DIR
from gimbal.prism.server.conversions import _draft_from_in, _redact_user
from gimbal.prism.state import DraftIn, UserIn  # back-compat re-export

__all__ = [
    "app",
    "STATIC_DIR",
    "DraftIn",
    "UserIn",
    "_draft_from_in",
    "_redact_user",
]