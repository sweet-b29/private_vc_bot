
def sanitize_name(name: str) -> str:
    bad = "@#:"
    clean = "".join(ch for ch in name if ch not in bad)
    return (clean[:24]).strip() or "room"
