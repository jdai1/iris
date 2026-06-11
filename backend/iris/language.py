from __future__ import annotations

import unicodedata


def looks_non_english(text: str, *, min_letters: int = 80, min_latin_ratio: float = 0.55) -> bool:
    letters = [char for char in text if char.isalpha()]
    if len(letters) < min_letters:
        return False
    latin_letters = [char for char in letters if "LATIN" in unicodedata.name(char, "")]
    return len(latin_letters) / len(letters) < min_latin_ratio
