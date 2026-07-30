# Siagnos

A personal fanfiction taste engine.

I read fanfiction on AO3 and FanFiction.net, and finding good fics is annoying. Tag search, filters, popularity rankings, none of it actually knows what I like. It matches keywords. I want something that learns from how I actually read: what I finish, what I drop after two chapters, what I come back to reread.

Siagnos tracks my reading sessions, builds a taste profile from that data, and scores unseen fics against it, explaining its reasoning instead of just spitting out a number. It's not a chatbot wrapper and it's not RAG. It's a taste model trained on my own behaviour, with its own feature extraction pipeline.

The content-similarity layer underneath that taste model comes from [Opsis](https://github.com/P-Kumar-18/Opsis), the internship project this grew out of. Opsis handles the similarity layer; Siagnos adds personal taste modelling trained on individual reading behaviour on top of it.

---

## 🚀 Current Features

- AO3 scraper with resume support and failure logging
- Cleaning, validation, and idempotent PostgreSQL loading, inherited directly from Opsis
- Semantic summary embeddings via `sentence-transformers/all-MiniLM-L6-v2`
- Hybrid ranking: semantic similarity, fandom overlap, relationship overlap, and popularity
- Normalized PostgreSQL schema, with a `behaviour` table and `rating_types` enum already in place, unpopulated until Stage 4
- Metadata-only AO3 collection; fanwork text is never stored
- Fic resolution by Work ID, URL, or title and author, and on-demand ingestion for works not already in the database, via `services/`

---

## 🧮 Ranking

Each summary becomes a 384-dimension vector. Candidates are retrieved by cosine similarity, then re-ranked:

```text
final_score =
    0.70 × embedding_similarity
  + 0.15 × fandom_similarity
  + 0.10 × relationship_similarity
  + 0.05 × popularity
```

Fandom and relationship overlap use Jaccard similarity; popularity is normalized kudos and bookmarks. These weights are fixed and inherited from Opsis, not yet learned. Replacing them with something trained on my own reading behaviour is the whole point of the stages ahead.

---

## 🔄 Pipeline Overview

```text
AO3 work
  → Scrape → clean → validate → normalize → insert → embed
  → Cosine similarity against stored embeddings
  → Batch metadata lookup
  → Hybrid re-ranking

Planned, not yet built:
  → Reading tracker logs sessions into the behaviour table
  → Feature engineering combines embeddings + scraped metadata + Ollama-derived tone/pacing
  → Preference model trained on that feature table, using reading behaviour as ground truth
  → Personal taste score, replacing the fixed ranking weights above
```

The initial dataset: 7,031 fics, 1,549 fandoms, 5,584 relationships, 5,785 characters, roughly 30K freeform tags, primarily My Hero Academia. Reached out to OTW before scraping at scale; they confirmed automated scraping is acceptable provided rate limits are respected and the project stays focused on metadata rather than fanwork content.

---

## 🧱 Project Structure

```text
Siagnos/
├── src/
│   ├── database/
│   │   └── schema.sql
│   ├── scraper/
│   │   └── scrape_ao3.py
│   ├── loader/
│   │   ├── config.py
│   │   ├── cleaner.py
│   │   ├── normalizer.py
│   │   ├── validator.py
│   │   ├── database.py
│   │   ├── inserter.py
│   │   └── load_ao3.py
│   ├── recommender/
│   │   ├── embedding_generator.py
│   │   ├── embedding_store.py
│   │   ├── pickle_store.py
│   │   ├── postgres_store.py
│   │   ├── similarity.py
│   │   ├── ranker.py
│   │   └── recommend.py
│   └── services/
│       ├── fic_resolver.py
│       ├── ingestion_service.py
│       ├── metadata.py
│       ├── format_author.py
│       └── normalize.py
├── data/
│   ├── raw/
│   ├── invalid/
│   ├── debugging/
│   └── processed/
├── experiments/
│   ├── embed_test.py
│   ├── generate
│   └── 
├── notebooks/
├── notes/
├── tests/
├── .gitignore
├── AO3_INQUIRY.md
├── requirements.txt
└── README.md
```

No `routes/`, `templates/`, or `static/` yet, those stay in Opsis until there's a reason to build Siagnos's own frontend on top of this.

---

## 🛠️ Setup Instructions

### 1. Create and activate a virtual environment

```bash
python -m venv venv
venv\Scripts\activate   # On Windows
```

### 2. Install dependencies

```bash
pip install torch==2.13.0 --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
```

### 3. Configure environment variables

```bash
cp .env.example .env
```

Set `DATABASE_URL` in `.env`. Never commit credentials.

### 4. Load the dataset

```bash
python -m src.loader.load_ao3
```

There's no `main.py` or web app to run yet. Recommendation logic runs directly through `src/recommender/recommend.py` for now.

---

## 📚 Tech Stack

- Python, FastAPI + Jinja2 (Stage 7), PostgreSQL (psycopg 3)
- HuggingFace Sentence Transformers for embeddings
- scikit-learn for similarity
- Ollama/NLP models for semantic tag mapping
- XGBoost / LightGBM for the preference model
- Docker, Azure for deployment
- cloudscraper, Beautiful Soup for AO3 collection

---

## 🎯 Project Status

**Early development**, building on top of a working, deployed sibling project (Opsis).

Implemented:

- [x] AO3 scraper with resume support and failure logging
- [x] Cleaning, validation, and idempotent PostgreSQL loading
- [x] MiniLM embeddings with PostgreSQL and pickle-backed storage
- [x] Hybrid ranking (semantic + fandom + relationship + popularity)
- [x] Normalized schema, with `behaviour` table and `rating_types` enum already in place
- [x] Fic resolution and on-demand ingestion for works not already in the database

Known limitations:

- No reading tracker yet, so the `behaviour` table is empty and the ranking weights above are fixed, not learned
- No FastAPI routes or frontend in this repo; the app-facing layer only exists in Opsis so far
- No Groq or equivalent explanation layer here
- Corpus is still MHA-centered, not representative of all of AO3

Still planned:

- [ ] Stage 4 — reading tracker, logging real sessions into the schema
- [ ] Stage 5 — feature engineering: embeddings + scraped metadata + Ollama-derived tone/pacing/dynamics, one feature table per fic
- [ ] Stage 6 — preference model trained on reading behaviour as ground truth against that feature table
- [ ] Stage 7 — FastAPI + Jinja2 backend, wiring up the model, embeddings, and database into a working API
- [ ] Stage 8 — frontend or browser extension
- [ ] Stage 9 — Docker + Azure deployment
- [ ] Stage 10 — write-up on what worked and what didn't

---

## 📝 License

TBD