def split_text(
    text: str,
    chunk_size: int = 500,
    chunk_overlap: int = 50
):
    """
    Split text into overlapping chunks.

    chunk_size:
        Maximum number of characters in each chunk.

    chunk_overlap:
        Number of characters shared between consecutive chunks.
    """

    if not text:
        return []

    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0")

    if chunk_overlap < 0:
        raise ValueError("chunk_overlap cannot be negative")

    if chunk_overlap >= chunk_size:
        raise ValueError(
            "chunk_overlap must be smaller than chunk_size"
        )

    chunks = []

    start = 0
    text_length = len(text)

    while start < text_length:

        end = start + chunk_size

        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        start = end - chunk_overlap

    return chunks