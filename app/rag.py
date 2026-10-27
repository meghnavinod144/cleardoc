"""RAG — Retrieval-Augmented Generation.

The open-book exam, in three moves:
  1. CHUNK: split the document text into small pieces.
  2. EMBED + STORE: turn each chunk into a vector (a list of numbers
     representing meaning) and keep it.
  3. RETRIEVE: when a question arrives, embed the question too, find the
     chunks whose vectors are closest, and hand ONLY those to the LLM:
     "answer using this, and nothing else."

Same socket pattern as llm.py: an Embedder interface, a mock for offline
development, and the real semantic embedder plugs in later without any
other file changing. The mock embeds by word overlap — cruder than real
semantic embeddings (it can't see that "power bill" ≈ "electricity
charges"), but the pipeline's SHAPE is identical.
"""

import hashlib
import json
import math
import re

DIMENSIONS = 256  # length of our vectors


class MockEmbedder:
    """Offline embedder: a hashed bag-of-words vector.

    Each word is hashed to one of 256 slots; the vector counts words per
    slot, then is normalized. Documents sharing words get similar vectors.
    Real semantic embedders (OpenAI, Voyage, Cohere — one API call) map
    MEANING, not just words, into ~1500 dimensions. Same socket.
    """

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * DIMENSIONS
        for word in re.findall(r"[a-z0-9]+", text.lower()):
            slot = int(hashlib.md5(word.encode()).hexdigest(), 16) % DIMENSIONS
            vector[slot] += 1.0
        length = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / length for v in vector]


def get_embedder():
    """Factory — real embedding provider plugs in here later."""
    return MockEmbedder()


def chunk_text(text: str, max_chars: int = 240) -> list[str]:
    """Split document text into retrieval-sized pieces.

    Why chunk at all? Retrieval precision: a question about the due date
    should fetch the 3 lines around 'Due Date', not the whole document.
    We split on lines and pack them into ~240-char chunks, never breaking
    a line in half (a bill's facts live on lines).
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    chunks, current = [], ""
    for line in lines:
        if len(current) + len(line) + 1 > max_chars and current:
            chunks.append(current)
            current = line
        else:
            current = f"{current}\n{line}" if current else line
    if current:
        chunks.append(current)
    return chunks


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """How close two vectors point: 1.0 = same direction, 0 = unrelated.
    This one formula is what 'vector search' ranks results with."""
    return sum(x * y for x, y in zip(a, b))  # vectors are pre-normalized


def retrieve(question: str, stored_chunks: list[dict], top_k: int = 3) -> list[dict]:
    """Find the chunks most similar to the question.

    stored_chunks: [{"text": ..., "embedding": [...], "position": n}, ...]
    Returns the top_k, each with its similarity score attached.
    """
    question_vector = get_embedder().embed(question)
    scored = [
        {**chunk, "score": round(cosine_similarity(question_vector, chunk["embedding"]), 3)}
        for chunk in stored_chunks
    ]
    scored.sort(key=lambda c: c["score"], reverse=True)
    return scored[:top_k]


ANSWER_PROMPT = """You are ClearDoc, an assistant that explains documents honestly.
Answer the user's question using ONLY the document excerpts below.
Rules:
- If the excerpts do not contain the answer, say you cannot find it in the
  document — never guess.
- Quote the exact figures from the excerpts when you use them.
- Be brief and plain-spoken.

DOCUMENT EXCERPTS:
{context}

QUESTION: {question}

ANSWER:"""


def build_answer_prompt(question: str, retrieved: list[dict]) -> str:
    context = "\n---\n".join(f"[excerpt {c['position']}] {c['text']}" for c in retrieved)
    return ANSWER_PROMPT.format(context=context, question=question)
