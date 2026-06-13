from sentence_transformers import SentenceTransformer
from sentence_transformers.util import cos_sim

# Small, fast, CPU-friendly model
model = SentenceTransformer('all-MiniLM-L6-v2')

# Replace these with real fic summaries of your choosing
summaries = [
    "A slow-burn enemies-to-lovers story where two rivals are forced to work together",
    "Two enemies must collaborate, and tension slowly turns to romance",
    "A lighthearted coffee shop AU with fluffy domestic moments",
]

embeddings = model.encode(summaries)

print(f"Embedding shape: {embeddings.shape}")
print(f"First few numbers of summary 1's embedding: {embeddings[0][:5]}")

print("\n--- Similarity Scores ---")
for i in range(len(summaries)):
    for j in range(i + 1, len(summaries)):
        score = cos_sim(embeddings[i], embeddings[j])
        print(f"Summary {i+1} vs Summary {j+1}: {score.item():.4f}")
        print(f"  '{summaries[i][:50]}...'")
        print(f"  '{summaries[j][:50]}...'")