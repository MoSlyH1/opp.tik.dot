"""Content sources. Every provider returns plain dicts with the same shape:

    {source, external_id, kind, url, title, author, description, thumbnail, tags, year?}

They never touch the database; app/store.py classifies and stores them.
"""
