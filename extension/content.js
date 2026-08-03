(() => {
  if (window.__irisHighlightingLoaded) return;
  window.__irisHighlightingLoaded = true;
  let pageState = null;
  let toolbar = null;
  let pendingHighlight = null;
  const blocked = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEXTAREA', 'INPUT', 'SELECT', 'OPTION', 'BUTTON']);

  const request = async (path, options = {}) => {
    const response = await chrome.runtime.sendMessage({ type: 'iris-request', path, options });
    if (!response?.ok) throw new Error(response?.status === 401 ? 'Sign in to Iris from the extension once' : response?.payload?.detail || response?.error || (response?.status ? `Iris returned HTTP ${response.status}` : 'Iris could not reach the server'));
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
    const existing = document.querySelector(`[data-iris-highlight-id="${highlight.uuid}"]`);
    if (existing) return existing;
    const range = locate(highlight); if (!range || range.collapsed) return false;
    const mark = document.createElement('mark'); mark.className = 'iris-highlight'; mark.dataset.irisHighlightId = highlight.uuid; mark.dataset.irisComment = String(Boolean(highlight.comment));
    try { range.surroundContents(mark); }
    catch {
      try { const contents = range.extractContents(); mark.append(contents); range.insertNode(mark); }
      catch { return false; }
    }
    mark.addEventListener('click', (event) => { event.stopPropagation(); openComment(highlight, mark.getBoundingClientRect()); });
    return mark;
  };

  const toast = (message) => { const el = document.createElement('div'); el.className = 'iris-toast'; el.textContent = message; document.body.append(el); setTimeout(() => el.remove(), 2200); };
  const closeToolbar = () => { toolbar?.remove(); toolbar = null; pendingHighlight = null; };
  const closeFloating = () => { closeToolbar(); document.querySelector('.iris-comment-popover')?.remove(); };
  const placeFloating = (element, rect, preference = 'above') => {
    const margin = 8, gap = 8, bounds = element.getBoundingClientRect();
    const left = Math.min(innerWidth - bounds.width - margin, Math.max(margin, rect.left + (rect.width / 2) - (bounds.width / 2)));
    let top = preference === 'below' ? rect.bottom + gap : rect.top - bounds.height - gap;
    if (top < margin) top = rect.bottom + gap;
    if (top + bounds.height > innerHeight - margin) top = Math.max(margin, rect.top - bounds.height - gap);
    element.style.left = `${left}px`; element.style.top = `${top}px`;
  };
  const openComment = (highlight, rect) => {
    closeFloating(); const pop = document.createElement('div'); pop.className = 'iris-comment-popover';
    pop.setAttribute('role', 'dialog'); pop.setAttribute('aria-label', 'Iris highlight note');
    pop.innerHTML = `<strong></strong><textarea aria-label="Highlight note" placeholder="Add a note…"></textarea><div class="iris-comment-actions"><button class="iris-delete">Delete</button><button class="iris-save">Save note</button></div>`;
    pop.querySelector('strong').textContent = highlight.quote; pop.querySelector('textarea').value = highlight.comment || '';
    document.body.append(pop); placeFloating(pop, rect, 'below'); pop.querySelector('textarea').focus();
    pop.querySelector('.iris-save').onclick = async () => {
      try {
        highlight = await request(`/api/highlights/${highlight.uuid}`, { method: 'PATCH', body: JSON.stringify({ comment: pop.querySelector('textarea').value.trim() || null }) });
        document.querySelector(`[data-iris-highlight-id="${highlight.uuid}"]`)?.setAttribute('data-iris-comment', String(Boolean(highlight.comment)));
        pop.remove(); toast('Highlight note saved');
      } catch (error) { toast(error.message || 'Could not save highlight note'); }
    };
    pop.querySelector('.iris-delete').onclick = async () => {
      try {
        await request(`/api/highlights/${highlight.uuid}`, { method: 'DELETE' });
        const rendered = document.querySelector(`[data-iris-highlight-id="${highlight.uuid}"]`);
        if (rendered) rendered.replaceWith(...rendered.childNodes);
        pop.remove(); toast('Highlight deleted');
      } catch (error) { toast(error.message || 'Could not delete highlight'); }
    };
  };

  const captureSelection = () => {
    const selection = getSelection(); if (!selection || selection.rangeCount !== 1 || selection.isCollapsed) return null;
    const range = selection.getRangeAt(0).cloneRange(); const rawQuote = selection.toString(); const quote = rawQuote.trim(); if (!quote) return null;
    const nodes = textNodes(), offsets = offsetsForRange(range, nodes), text = pageText(nodes);
    if (offsets.start == null || offsets.end == null) return null;
    const leading = rawQuote.length - rawQuote.trimStart().length, trailing = rawQuote.length - rawQuote.trimEnd().length;
    offsets.start += leading; offsets.end -= trailing;
    return {
      rect: range.getBoundingClientRect(),
      payload: { quote, prefix: text.slice(Math.max(0, offsets.start - 64), offsets.start), suffix: text.slice(offsets.end, offsets.end + 64), start_offset: offsets.start, end_offset: offsets.end },
    };
  };

  const rememberPage = async (page) => {
    if (!page?.entry) return;
    const stored = await chrome.storage.local.get({ savedUrls: [] });
    const existingUrls = Array.isArray(stored.savedUrls) ? stored.savedUrls : [];
    const savedUrls = [...new Set([...existingUrls, location.href, page.entry.document.url])].slice(-2000);
    await chrome.storage.local.set({ savedUrls });
  };

  const ensurePage = async () => {
    if (pageState?.entry) return pageState;
    const page = await request('/api/browser/pages/capture', {
      method: 'POST',
      body: JSON.stringify({ url: location.href, title: document.title || null, crawl_now: false }),
    });
    if (!page?.entry) throw new Error('Iris could not save this page');
    activate(page); rememberPage(page).catch(() => {}); return page;
  };

  const createHighlight = async (withNote = false) => {
    const captured = pendingHighlight;
    if (!captured || toolbar?.dataset.busy === 'true') return;
    toolbar.dataset.busy = 'true';
    const buttons = [...toolbar.querySelectorAll('button')];
    buttons.forEach((button) => { button.disabled = true; });
    const highlightButton = toolbar.querySelector('[data-action="highlight"]');
    if (highlightButton) highlightButton.textContent = 'Saving…';
    try {
      const page = await ensurePage();
      const created = await request(`/api/documents/${page.entry.document.uuid}/highlights`, { method: 'POST', body: JSON.stringify(captured.payload) });
      getSelection()?.removeAllRanges();
      const rendered = renderHighlight(created); closeToolbar();
      if (withNote && rendered) openComment(created, rendered.getBoundingClientRect());
      else toast('Highlighted in Iris');
    } catch (error) { closeToolbar(); toast(error.message || 'Could not save highlight'); }
  };

  document.addEventListener('mouseup', (event) => {
    if (event.target instanceof Element && event.target.closest('.iris-selection-toolbar,.iris-comment-popover')) return;
    setTimeout(() => {
      const captured = captureSelection();
      if (!captured) { closeToolbar(); return; }
      closeFloating(); pendingHighlight = captured;
      toolbar = document.createElement('div'); toolbar.className = 'iris-selection-toolbar'; toolbar.setAttribute('role', 'toolbar'); toolbar.setAttribute('aria-label', 'Save selection to Iris');
      toolbar.innerHTML = `<span class="iris-toolbar-brand"><img src="${chrome.runtime.getURL('icons/iris-mark.svg')}" alt="" aria-hidden="true"><span>iris</span></span><button data-action="highlight">Highlight</button><button class="iris-note-action" data-action="note" aria-label="Highlight with note" title="Highlight with note"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z"></path><path d="M12 8v6M9 11h6"></path></svg></button>`;
      document.body.append(toolbar); placeFloating(toolbar, captured.rect);
      toolbar.querySelectorAll('button').forEach((button) => button.addEventListener('pointerdown', (buttonEvent) => buttonEvent.preventDefault()));
      toolbar.querySelector('[data-action="highlight"]').addEventListener('click', () => createHighlight(false));
      toolbar.querySelector('[data-action="note"]').addEventListener('click', () => createHighlight(true));
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
