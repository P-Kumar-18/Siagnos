LIST_COLUMNS = [
    'warning',
    'category',
    'fandom',
    'relationship',
    'character',
    'freeform'
]

INTEGER_COLUMNS = [
    'words',
    'kudos',
    'bookmarks',
    'hits',
    'current_chapters',
    'total_chapters'
]

TEXT_COLUMNS = [
    'title',
    'author',
    'summary',
    'rating',
    'language',
    'status',
    'url'
]

DEFAULT_ZERO_COLUMNS = [
    'hits',
    'kudos',
    'bookmarks'
]

TABLE_CONFIG = [
    ('warning', 'warning_id', 'warning'),
    ('category', 'categories_id', 'categories'),
    ('fandom', 'fandom_id', 'fandom'),
    ('relationship', 'relationship_id', 'relationship'),
    ('character', 'characters_id', 'characters'),
    ('freeform', 'freeform_id', 'freeform')
]

FIC_COLUMNS =[
    'fic_id',
    'url',
    'title',
    'author',
    'summary',
    'hits',
    'bookmarks',
    'kudos',
    'current_chapters',
    'total_chapters',
    'words',
    'last_date',
    'status',
    'language',
    'rating'
]

VALUE_TABLE_MAPPING = {
    "warning": ("warning_value", "warning_id", "warning"),
    "category": ("categories_value", "categories_id", "categories"),
    "fandom": ("fandom_value", "fandom_id", "fandom"),
    "relationship": ("relationship_value", "relationship_id", "relationship"),
    "character": ("characters_value", "characters_id", "characters"),
    "freeform": ("freeform_value", "freeform_id", "freeform"),
}

JOIN_TABLE_MAPPING = {
    "warning": "warning_join",
    "category": "categories_join",
    "fandom": "fandom_join",
    "relationship": "relationship_join",
    "character": "characters_join",
    "freeform": "freeform_join",
}