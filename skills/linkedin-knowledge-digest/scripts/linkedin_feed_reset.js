(() => {
  try {
    sessionStorage.removeItem("__codexLinkedInDigestSessionV1");
  } catch {
    // A fresh in-memory session still works when storage is unavailable.
  }
  window.__codexLinkedInDigestSession = undefined;
  return JSON.stringify({ ok: true });
})();
