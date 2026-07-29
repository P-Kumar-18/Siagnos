from src.loader import get_connection
from src.services import populate_metadata, populate_metadata_many


class FicResolver:
    """Service class for resolving fanfiction records from ID, URL, or author metadata."""

    def __init__(self, input: dict):
        self.input = input

    @staticmethod
    def resolve_many_from_ids(fic_ids: list[int]) -> list[dict]:
        """Fetch multiple fic records and their metadata in batch."""

        if not fic_ids:
            return []

        fic_ids = [int(fic_id) for fic_id in fic_ids]

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM fics
                    WHERE fic_id = ANY(%s)
                    """,
                    (fic_ids,),
                )

                results = cur.fetchall()

                if not results:
                    return []

                columns = [desc[0] for desc in cur.description]

                fics_by_id = {
                    row[columns.index("fic_id")]: dict(zip(columns, row))
                    for row in results
                }

                # Restore the recommendation order because SQL does not
                # guarantee the same ordering as fic_ids.
                fics = [
                    fics_by_id[fic_id]
                    for fic_id in fic_ids
                    if fic_id in fics_by_id
                ]

                return populate_metadata_many(cur, fics)

    def resolve_from_id(self):
        """Fetch fic record directly using primary key ID."""
        fic_id = self.input["fic_id"]

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM fics WHERE fic_id = %s", (fic_id,))
                result = cur.fetchone()

                if result:
                    fic = dict(zip([desc[0] for desc in cur.description], result))
                    return populate_metadata(cur, fic)

                return {"error": f"No fic found with id: {fic_id}"}

    def resolve_from_url(self):
        """Fetch fic record matching canonical AO3 URL."""
        url = f"{self.input['url']}?view_adult=true"

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM fics WHERE url = %s", (url,))
                result = cur.fetchone()

                if result:
                    fic = dict(zip([desc[0] for desc in cur.description], result))
                    return populate_metadata(cur, fic)

                return {"error": f"No fic found with url: {url}"}

    def resolve_from_name_author(self):
        """Fetch fic record using work name and formatted author path."""
        name = self.input["name"]
        author = f"/users/{self.input['author']}/pseuds/{self.input['author']}"

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM fics WHERE name = %s AND author = %s", (name, author))
                result = cur.fetchone()

                if result:
                    fic = dict(zip([desc[0] for desc in cur.description], result))
                    return populate_metadata(cur, fic)

                return {"error": "No fic found with exact name and author"}

    def resolve(self):
        """Dispatch resolution based on payload structure and validate parameters."""
        if len(self.input) == 1:
            if "fic_id" in self.input:
                try:
                    int(self.input["fic_id"])
                except (ValueError, TypeError):
                    return {"error": "Invalid 'fic_id' value. It must be a numeric string."}

                return self.resolve_from_id()

            elif "url" in self.input:
                url = self.input["url"]

                if url.startswith("http://") or url.startswith("https://"):
                    if "/chapters/" in url:
                        self.input["url"] = url.split("/chapters/")[0]

                    return self.resolve_from_url()

                return {"error": "Invalid 'url' value. It must be a valid HTTP or HTTPS URL."}

        elif len(self.input) == 2 and "name" in self.input and "author" in self.input:
            if self.input["name"].strip() and self.input["author"].strip():
                return self.resolve_from_name_author()

        return {"error": "Invalid input. Please provide either an 'id', a 'url', or both 'name' and 'author'."}