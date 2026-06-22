# Siagnos

A personal fanfiction taste engine.

## Why I'm building this

I read fanfiction on AO3 and FanFiction.net, and finding good fics is annoying. Tag search, filters, popularity rankings, none of it actually knows what I like. It matches keywords. I want something that learns from how I actually read: what I finish, what I drop after two chapters, what I come back to reread.

So I'm building that. A system trained on my own reading behaviour that scores new fics against my taste and tells me why.

## What it does

Siagnos tracks my reading sessions (what I open, how far I get, whether I return), builds a taste profile from that data, and scores unseen fics against it. It explains its reasoning instead of just spitting out a number.

It's not a chatbot wrapper and it's not RAG. It's a taste model trained on my own behaviour, with its own feature extraction pipeline built from embeddings and local NLP text processing utilities for tag analysis.

## Status

**Early development.** 

Currently on Stage:
- Stage 1: embeddings pipeline. *(done)*
- Stage 2: date collection.

## Tech stack

- Python, FastAPI, PostgreSQL
- HuggingFace Sentence Transformers for embeddings
- Ollama/NLP models for semantic tag mapping
- XGBoost / LightGBM for the preference model
- Docker, Azure for deployment

## Setup

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

## License

TBD