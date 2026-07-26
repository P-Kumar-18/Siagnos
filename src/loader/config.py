# Columns containing list or array formatted values in raw data
LIST_COLUMNS = [
    'warning',
    'category',
    'fandom',
    'relationship',
    'character',
    'freeform'
]


# Columns representing numerical values requiring safe integer conversion
INTEGER_COLUMNS = [
    'words',
    'kudos',
    'bookmarks',
    'hits',
    'current_chapters',
    'total_chapters'
]


# Columns representing standard textual descriptive metadata fields
TEXT_COLUMNS = [
    'title',
    'author',
    'summary',
    'rating',
    'language',
    'status',
    'url'
]


# Numerical columns that must default to zero when null/missing
DEFAULT_ZERO_COLUMNS = [
    'hits',
    'kudos',
    'bookmarks'
]


# Configuration tuples used to define and normalize many-to-many relationship structures
# Format: (source_column, primary_key, table_name)
TABLE_CONFIG = [
    ('warning', 'warning_id', 'warning'),
    ('category', 'categories_id', 'categories'),
    ('fandom', 'fandom_id', 'fandom'),
    ('relationship', 'relationship_id', 'relationship'),
    ('character', 'characters_id', 'characters'),
    ('freeform', 'freeform_id', 'freeform')
]


# Standard column ordering and schema definitions for the primary fanfiction table
FIC_COLUMNS = [
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


# Mappings associating metadata attributes with target value tables and primary/foreign keys
# Format: "source_field": ("value_column", "id_column", "target_table_name")
VALUE_TABLE_MAPPING = {
    "warning": ("warning_value", "warning_id", "warning"),
    "category": ("categories_value", "categories_id", "categories"),
    "fandom": ("fandom_value", "fandom_id", "fandom"),
    "relationship": ("relationship_value", "relationship_id", "relationship"),
    "character": ("characters_value", "characters_id", "characters"),
    "freeform": ("freeform_value", "freeform_id", "freeform"),
}


# Mappings linking metadata attributes to their respective intermediary database join tables
JOIN_TABLE_MAPPING = {
    "warning": "warning_join",
    "category": "categories_join",
    "fandom": "fandom_join",
    "relationship": "relationship_join",
    "character": "characters_join",
    "freeform": "freeform_join",
}