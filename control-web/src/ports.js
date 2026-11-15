/** Build the Board site URL from the address the visitor is on. */
export function boardUrl(boardPort) {
  if (typeof window === "undefined") {
    return `http://127.0.0.1:${boardPort || 7410}/`;
  }
  const port = boardPort || 7410;
  return `${window.location.protocol}//${window.location.hostname}:${port}/`;
}

export function controlUrl(controlPort) {
  if (typeof window === "undefined") {
    return `http://127.0.0.1:${controlPort || 7411}/`;
  }
  const port = controlPort || 7411;
  return `${window.location.protocol}//${window.location.hostname}:${port}/`;
}
