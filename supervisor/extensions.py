"""Optional extensions for Control.

An extension is a Python module that adds routes and sign in buttons to
Control. Nothing in this repo needs one, and Control works the same without
any. StarFerret's own add ons and anyone's fork can use the same hook.

Turn one on by naming its module in ``STARFERRET_EXTENSIONS`` (comma separated)
and putting it on the Python path. Control imports each module once at start
and calls its ``register(ctx)`` with the ``ExtensionContext`` below. A module
that fails to load is skipped with a line in the log; Control keeps running.
"""

from __future__ import annotations

import importlib
import logging
import os
from typing import Any, Callable

log = logging.getLogger(__name__)

ENV_VAR = "STARFERRET_EXTENSIONS"


class ExtensionContext:
    """What an extension may use. Keep this small and stable: forks depend on it."""

    def __init__(
        self,
        app,
        store,
        require_auth: Callable[..., Callable],
        current_user: Callable[[], Any],
        start_session: Callable[[Any, dict], Any],
        fail_sign_in: Callable[[str], Any],
    ) -> None:
        self.app = app
        """The Control Flask app. Add routes under ``/api/control/<your name>/``."""
        self.store = store
        """``supervisor.store``: users, sessions, settings, and ``cursor()`` for your own tables."""
        self.require_auth = require_auth
        """Decorator: ``@ctx.require_auth("admin")``. Same roles as Control's own routes."""
        self.current_user = current_user
        """The signed in Control user, or None."""
        self.start_session = start_session
        """``start_session(response, user)`` signs ``user`` in on ``response`` and returns it."""
        self.fail_sign_in = fail_sign_in
        """``fail_sign_in(message)`` returns a redirect to the sign in screen that shows ``message`` once."""
        self._sign_in_options: list[Callable[[], list[dict]]] = []

    def add_sign_in_options(self, provider: Callable[[], list[dict]]) -> None:
        """Add buttons to Control's sign in screen.

        ``provider()`` is called on every page load and returns
        ``[{"id": ..., "label": ..., "url": ...}]``. Return an empty list to
        show nothing (for example while the option is not set up).
        """
        self._sign_in_options.append(provider)

    def sign_in_options(self) -> list[dict]:
        out: list[dict] = []
        for provider in self._sign_in_options:
            try:
                for item in provider() or []:
                    if item.get("id") and item.get("label") and item.get("url"):
                        out.append({"id": str(item["id"]), "label": str(item["label"]), "url": str(item["url"])})
            except Exception:  # an extension must never break the sign in screen
                log.exception("Sign in options from an extension failed")
        return out


def load(ctx: ExtensionContext) -> list[str]:
    """Import and register every module named in STARFERRET_EXTENSIONS. Returns the ones loaded."""
    loaded: list[str] = []
    for name in (os.environ.get(ENV_VAR) or "").split(","):
        name = name.strip()
        if not name:
            continue
        try:
            module = importlib.import_module(name)
            module.register(ctx)
            loaded.append(name)
            log.info("Loaded Control extension %s", name)
        except Exception:
            log.exception("Could not load Control extension %s; Control runs without it", name)
    return loaded
