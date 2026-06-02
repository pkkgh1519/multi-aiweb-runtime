from __future__ import annotations

# Kept as a single string so future Playwright/CDP code can inject one audited observer.
CDP_OBSERVER_SCRIPT = r"""
(() => {
  if (window.__chatgptWebRuntimeObserver) return window.__chatgptWebRuntimeObserver;
  const state = { installedAt: Date.now(), sequence: 0, latest: null };
  function text(node) { return (node && (node.innerText || node.textContent) || '').trim(); }
  function latest(role) {
    const nodes = Array.from(document.querySelectorAll(`[data-message-author-role="${role}"]`));
    const node = nodes[nodes.length - 1] || null;
    return { node, text: text(node) };
  }
  function snapshot() {
    const user = latest('user');
    const assistant = latest('assistant');
    const buttons = Array.from(document.querySelectorAll('button,[role="button"]')).map(b => text(b) || b.getAttribute('aria-label') || '');
    const stopVisible = buttons.some(label => /stop|중지/i.test(label));
    const actionVisible = buttons.some(label => /copy|regenerate|복사|다시/i.test(label));
    const status = assistant.text && !stopVisible && actionVisible ? 'done' : assistant.text ? 'streaming' : user.text ? 'thinking' : 'idle';
    state.latest = { sequence: ++state.sequence, status, userText: user.text, assistantText: assistant.text, stopVisible, actionVisible, url: location.href };
    return state.latest;
  }
  const observer = new MutationObserver(snapshot);
  observer.observe(document.documentElement, { childList: true, subtree: true, characterData: true, attributes: true });
  state.snapshot = snapshot;
  window.__chatgptWebRuntimeObserver = state;
  snapshot();
  return state;
})();
"""
