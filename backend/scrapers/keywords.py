STOP_WORDS = {
    "for", "with", "the", "a", "an", "and", "or", "but", "in", "on", "at",
    "to", "of", "that", "this", "is", "are", "was", "be", "by", "from",
    "my", "your", "our", "their", "i", "it", "its", "me", "we", "you",
    "best", "good", "great", "nice", "new", "buy", "get", "find",
}


def to_keywords(phrase: str) -> list[str]:
    words = phrase.lower().strip().split()
    keywords = [w.strip(".,!?") for w in words if w.strip(".,!?") not in STOP_WORDS and len(w) > 1]
    return keywords if keywords else words


def to_query_string(phrase: str) -> str:
    return "+".join(to_keywords(phrase))
