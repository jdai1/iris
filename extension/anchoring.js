globalThis.IrisAnchoring = {
  locateOffsets(text, highlight) {
    if (highlight.start_offset != null && highlight.end_offset != null && text.slice(highlight.start_offset, highlight.end_offset) === highlight.quote) {
      return { start: highlight.start_offset, end: highlight.end_offset, strategy: 'position' };
    }
    let from = 0;
    while ((from = text.indexOf(highlight.quote, from)) !== -1) {
      const prefixOk = !highlight.prefix || text.slice(Math.max(0, from - highlight.prefix.length), from) === highlight.prefix;
      const end = from + highlight.quote.length;
      const suffixOk = !highlight.suffix || text.slice(end, end + highlight.suffix.length) === highlight.suffix;
      if (prefixOk && suffixOk) return { start: from, end, strategy: 'quote' };
      from += Math.max(1, highlight.quote.length);
    }
    return null;
  },
};
