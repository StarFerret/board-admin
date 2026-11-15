"""StarFerret Control plane — separate from the Board Flask process.

Owns admin auth, app catalog (Compose), model library helpers, health, and
Board process lifecycle. Privileged Docker / installer work stays here, never
inside the agent sandbox harness.
"""

__version__ = "0.1.0"
