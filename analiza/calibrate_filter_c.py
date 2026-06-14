"""Kalibracja progu Filtra C: rozkład cosine similarity do konceptu aksjologicznego
na pełnym korpusie. Nie zapisuje filtra — tylko diagnostyka do wyboru progu."""
import json
from pathlib import Path
import numpy as np
from sentence_transformers import SentenceTransformer
from filter_value_frames_lib import AXIOLOGICAL_CONCEPT, build_concept_embedding
from sklearn.metrics.pairwise import cosine_similarity

OUT = Path(__file__).parent / "out"
posts = [json.loads(l) for l in (OUT / "posts_flat.jsonl").open(encoding="utf-8")]
texts = [str(p.get("text") or "") for p in posts]
nonempty = [(i, t) for i, t in enumerate(texts) if t and t.strip()]
idx, valid = zip(*nonempty)
print(f"posts={len(posts)} nonempty={len(valid)}")

model = SentenceTransformer("all-mpnet-base-v2")
print("device:", model.device)
concept = build_concept_embedding(model)
emb = model.encode(list(valid), batch_size=128, show_progress_bar=True)
sims = cosine_similarity(emb, concept.reshape(1, -1)).flatten()

pct = [50, 60, 66, 70, 75, 80, 85, 90, 95, 99]
print("\n=== Percentyle cosine sim ===")
for p in pct:
    print(f"  p{p:>2}: {np.percentile(sims, p):.4f}")
print(f"  max: {sims.max():.4f}  mean: {sims.mean():.4f}")

print("\n=== Pass-rate per próg (denominator = nonempty) ===")
for thr in [0.08, 0.10, 0.12, 0.14, 0.15, 0.16, 0.18, 0.20, 0.25, 0.28]:
    passed = int((sims >= thr).sum())
    print(f"  thr={thr:.2f}  passed={passed:>6}  ({passed/len(valid)*100:5.1f}%)")
