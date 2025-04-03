from .model import ParsingRetryException

def parse_response(text: str, tags: list[str]) -> dict:
    res = {}
    for t in tags:
        res[t] = xmlparse(text, t)
    return res

def xmlparse(text: str, tag: str):
    prev = 0
    try:
        start = text.index(f"<{tag}>", prev, len(text)) + 2 + len(tag)
        if f"</{tag}>" not in text:
            return text[start:]

        end = text.index(f"</{tag}>", prev, len(text))
        return text[start:end]
    except Exception:
        raise ParsingRetryException(
            message=f"<{tag}> tag was unable to be parsed from text, \n\n{text}`",
            text=text,
            tag=tag,
        )