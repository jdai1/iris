(() => {
  if (window.__irisHighlightingLoaded) return;
  window.__irisHighlightingLoaded = true;
  let pageState = null;
  let toolbar = null;
  let pendingHighlight = null;
  const blocked = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEXTAREA', 'INPUT', 'SELECT', 'OPTION', 'BUTTON']);

  const request = async (path, options = {}) => {
    const response = await chrome.runtime.sendMessage({ type: 'iris-request', path, options });
    if (!response?.ok) throw new Error(response?.status === 401 ? 'Sign in to Iris again' : response?.payload?.detail || response?.error || `Iris returned HTTP ${response?.status}`);
    return response.payload;
  };

  const textNodes = () => {
    const nodes = [];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        const parent = node.parentElement;
        if (!parent || blocked.has(parent.tagName) || parent.closest('.iris-selection-toolbar,.iris-comment-popover,[contenteditable="true"]')) return NodeFilter.FILTER_REJECT;
        return node.nodeValue ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
      },
    });
    while (walker.nextNode()) nodes.push(walker.currentNode);
    return nodes;
  };

  const pageText = (nodes = textNodes()) => nodes.map((node) => node.nodeValue).join('');
  const offsetsForRange = (range, nodes) => {
    let cursor = 0, start = null, end = null;
    for (const node of nodes) {
      if (node === range.startContainer) start = cursor + range.startOffset;
      if (node === range.endContainer) end = cursor + range.endOffset;
      cursor += node.nodeValue.length;
    }
    return { start, end };
  };
  const rangeForOffsets = (start, end, nodes) => {
    let cursor = 0, startNode, endNode, startOffset, endOffset;
    for (const node of nodes) {
      const next = cursor + node.nodeValue.length;
      if (!startNode && start >= cursor && start <= next) { startNode = node; startOffset = start - cursor; }
      if (!endNode && end >= cursor && end <= next) { endNode = node; endOffset = end - cursor; break; }
      cursor = next;
    }
    if (!startNode || !endNode) return null;
    const range = document.createRange(); range.setStart(startNode, startOffset); range.setEnd(endNode, endOffset); return range;
  };
  const locate = (highlight) => {
    const nodes = textNodes(), text = pageText(nodes);
    const located = IrisAnchoring.locateOffsets(text, highlight);
    return located ? rangeForOffsets(located.start, located.end, nodes) : null;
  };

  const renderHighlight = (highlight) => {
    if (document.querySelector(`[data-iris-highlight-id="${highlight.id}"]`)) return true;
    const range = locate(highlight); if (!range || range.collapsed) return false;
    const mark = document.createElement('mark'); mark.className = 'iris-highlight'; mark.dataset.irisHighlightId = highlight.id; mark.dataset.irisComment = String(Boolean(highlight.comment));
    try { range.surroundContents(mark); }
    catch {
      try { const contents = range.extractContents(); mark.append(contents); range.insertNode(mark); }
      catch { return false; }
    }
    mark.addEventListener('click', (event) => { event.stopPropagation(); openComment(highlight, mark.getBoundingClientRect()); });
    return true;
  };

  const toast = (message) => { const el = document.createElement('div'); el.className = 'iris-toast'; el.textContent = message; document.body.append(el); setTimeout(() => el.remove(), 2200); };
  const closeToolbar = () => { toolbar?.remove(); toolbar = null; pendingHighlight = null; };
  const closeFloating = () => { closeToolbar(); document.querySelector('.iris-comment-popover')?.remove(); };
  const openComment = (highlight, rect) => {
    closeFloating(); const pop = document.createElement('div'); pop.className = 'iris-comment-popover';
    pop.innerHTML = `<strong></strong><textarea placeholder="Add a note to this highlight…"></textarea><div class="iris-comment-actions"><button class="iris-delete">Delete highlight</button><button class="iris-save">Save note</button></div>`;
    pop.querySelector('strong').textContent = highlight.quote; pop.querySelector('textarea').value = highlight.comment || '';
    pop.style.left = `${Math.min(innerWidth - 296, Math.max(8, rect.left))}px`; pop.style.top = `${Math.min(innerHeight - 180, rect.bottom + 8)}px`; document.body.append(pop);
    pop.querySelector('.iris-save').onclick = async () => { highlight = await request(`/api/highlights/${highlight.id}`, { method: 'PATCH', body: JSON.stringify({ comment: pop.querySelector('textarea').value.trim() || null }) }); document.querySelector(`[data-iris-highlight-id="${highlight.id}"]`)?.setAttribute('data-iris-comment', String(Boolean(highlight.comment))); pop.remove(); toast('Highlight note saved'); };
    pop.querySelector('.iris-delete').onclick = async () => { await request(`/api/highlights/${highlight.id}`, { method: 'DELETE' }); document.querySelector(`[data-iris-highlight-id="${highlight.id}"]`)?.replaceWith(...document.querySelector(`[data-iris-highlight-id="${highlight.id}"]`).childNodes); pop.remove(); toast('Highlight deleted'); };
  };

  const captureSelection = () => {
    const selection = getSelection(); if (!selection || selection.rangeCount !== 1 || selection.isCollapsed) return null;
    const range = selection.getRangeAt(0).cloneRange(); const rawQuote = selection.toString(); const quote = rawQuote.trim(); if (!quote || !pageState?.entry) return null;
    const nodes = textNodes(), offsets = offsetsForRange(range, nodes), text = pageText(nodes);
    if (offsets.start == null || offsets.end == null) return null;
    const leading = rawQuote.length - rawQuote.trimStart().length, trailing = rawQuote.length - rawQuote.trimEnd().length;
    offsets.start += leading; offsets.end -= trailing;
    return {
      rect: range.getBoundingClientRect(),
      payload: { quote, prefix: text.slice(Math.max(0, offsets.start - 64), offsets.start), suffix: text.slice(offsets.end, offsets.end + 64), start_offset: offsets.start, end_offset: offsets.end },
    };
  };

  const createHighlight = async () => {
    const captured = pendingHighlight;
    if (!captured || !pageState?.entry) return;
    closeToolbar();
    try {
      const created = await request(`/api/documents/${pageState.entry.document.id}/highlights`, { method: 'POST', body: JSON.stringify(captured.payload) });
      getSelection()?.removeAllRanges(); renderHighlight(created); toast('Highlight saved to Iris');
    } catch (error) { toast(error.message || 'Could not save highlight'); }
  };

  document.addEventListener('mouseup', (event) => {
    if (event.target instanceof Element && event.target.closest('.iris-selection-toolbar,.iris-comment-popover')) return;
    setTimeout(() => {
      if (!pageState?.saved) return;
      const captured = captureSelection();
      if (!captured) { closeToolbar(); return; }
      closeFloating(); pendingHighlight = captured;
      toolbar = document.createElement('div'); toolbar.className = 'iris-selection-toolbar'; toolbar.setAttribute('role', 'toolbar'); toolbar.setAttribute('aria-label', 'Save selection to Iris'); toolbar.innerHTML = '<span class="iris-toolbar-brand">iris</span><button>Highlight</button>';
      toolbar.style.left = `${Math.min(innerWidth - 176, Math.max(8, captured.rect.left + (captured.rect.width / 2) - 88))}px`; toolbar.style.top = `${Math.max(8, captured.rect.top - 44)}px`; document.body.append(toolbar);
      const button = toolbar.querySelector('button');
      button.addEventListener('pointerdown', (buttonEvent) => buttonEvent.preventDefault());
      button.addEventListener('click', createHighlight);
    }, 0);
  });

  document.addEventListener('pointerdown', (event) => {
    if (toolbar && !toolbar.contains(event.target)) closeToolbar();
    const popover = document.querySelector('.iris-comment-popover');
    const targetHighlight = event.target instanceof Element ? event.target.closest('.iris-highlight') : null;
    if (popover && !popover.contains(event.target) && !targetHighlight) popover.remove();
  }, true);
  document.addEventListener('selectionchange', () => {
    const selection = getSelection();
    if (toolbar && (!selection || selection.isCollapsed || !selection.toString().trim())) closeToolbar();
  });
  document.addEventListener('keydown', (event) => { if (event.key === 'Escape') closeFloating(); });
  window.addEventListener('resize', closeFloating);

  const activate = (page) => {
    pageState = page;
    [...page.highlights].sort((a, b) => (b.start_offset ?? 0) - (a.start_offset ?? 0)).forEach(renderHighlight);
  };
  chrome.runtime.onMessage.addListener((message) => { if (message?.type === 'iris-page-saved') activate(message.page); });
  chrome.storage.local.get({ savedUrls: [] }).then(({ savedUrls }) => {
    const candidate = new URL(location.href); [...candidate.searchParams.keys()].filter((key) => key.startsWith('utm_')).forEach((key) => candidate.searchParams.delete(key)); candidate.hash = '';
    if (!savedUrls.includes(location.href) && !savedUrls.includes(candidate.toString())) return;
    request(`/api/browser/pages/resolve?url=${encodeURIComponent(location.href)}`).then((page) => { if (page.saved) activate(page); }).catch(() => {});
  });
})();
