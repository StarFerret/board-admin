import os
import socket
import sys

from .app import _port_available, app, socketio
from .paths import DEFAULT_PORT

if __name__ == "__main__":
    port = int(os.environ.get("PORT", str(DEFAULT_PORT)))
    if not _port_available(port):
        print(
            f"Port {port} is already in use. Stop other StarFerret servers "
            f"(Task Manager → python.exe on port {port}) and try again.",
            file=sys.stderr,
        )
        sys.exit(1)
    # macOS can hang forever in socket.getfqdn → gethostbyaddr during bind.
    socket.getfqdn = lambda name="": "localhost"
    socketio.run(app, host="0.0.0.0", port=port, allow_unsafe_werkzeug=True)
