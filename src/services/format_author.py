def format_author(author: str | None) -> str:
    """Extract canonical username from AO3 user URL path or return default fallback."""
    if author is None:
        return "Anonymous"

    if "/users/" in author:
        return author.split("/users/", 1)[1].split("/", 1)[0]

    return author