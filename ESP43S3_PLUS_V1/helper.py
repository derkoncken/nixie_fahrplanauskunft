# helper.py
def split_string(s: str, length: int):
    s = "" if s is None else str(s)
    s1 = s[:length]
    rest = s[length:]
    if rest:
        s2 = rest[:max(0, length - 2)] + ".."
    else:
        s2 = ""
    return s1, s2


def normalize_text(s):
    if not isinstance(s, str):
        s = str(s)
    repl = {
        "Ä": "Ae", "Ö": "Oe", "Ü": "Ue",
        "ä": "ae", "ö": "oe", "ü": "ue",
        "ß": "ss",
        "→": "->",
    }
    for k, v in repl.items():
        s = s.replace(k, v)
    return s
