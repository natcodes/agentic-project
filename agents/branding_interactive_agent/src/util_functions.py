import os
import json
import logging

import psycopg2
from psycopg2.extras import RealDictCursor

from openai import OpenAI
# from prompts import BRANDING_FINAL_PROMPT

#prompts: 

BRANDING_FINAL_PROMPT="""You are a senior brand strategist helping a small service-based business.

You are given:
1) An optional service description from the database (may be empty).
2) Answers from an interactive brand workshop.

Service description (JSON):
{service_description}

Workshop answers (JSON):
{answers_json}

Using this information, create a clear, concise BrandIdentityMap in JSON with the following EXACT keys:

{{
  "brand_name": "string",
  "tagline": "string",
  "mission": "string",
  "vision": "string or null",
  "values": ["string", "..."],
  "uniqueValueProposition": "string",
  "toneOfVoice": {{
    "primaryDescriptors": ["string", "..."],
    "doSayExamples": ["string", "..."],
    "dontSayExamples": ["string", "..."]
  }},
  "audiencePersonas": [
    {{
      "name": "string",
      "ageRange": "string or null",
      "occupation": "string or null",
      "shortBio": "string",
      "goals": ["string", "..."],
      "frustrations": ["string", "..."],
      "favoritePlatforms": ["string", "..."]
    }}
  ],
  "visualDirection": {{
    "colors": ["string", "..."],
    "styles": ["string", "..."],
    "logoDescription": "string",
    "inspirationKeywords": ["string", "..."]
  }},
  "brandStory": "string"
}}

Guidelines:
- Infer a sensible brand_name if the user did not specify one explicitly.
- Derive the tagline, mission, and uniqueValueProposition from the service summary and core brand message.
- Turn the raw values & tone text into:
  - 3–7 values
  - 3–6 primaryDescriptors
  - 2–4 "doSayExamples"
  - 2–4 "dontSayExamples"
- Turn the audience description into 1–2 personas that match the goals and frustrations.
- Turn the visuals text into colors, styles, logoDescription, and inspirationKeywords.
- If you are unsure about a field, make a reasonable guess based on the answers and keep it simple.

Output:
- Respond with JSON ONLY.
- Do not include any comments, explanations, or markdown – just a single JSON object.
"""




# ---------- DB CONNECTION HELPERS ----------

PG_HOST = os.getenv("PGHOST", "localhost")
PG_PORT = int(os.getenv("PGPORT", "5432"))
PG_DBNAME = os.getenv("PGDATABASE", "ideaction")
PG_USER = os.getenv("PGUSER", "postgres")
PG_PASSWORD = os.getenv("PGPASSWORD", "")

def _get_db_connection():
    """
    Returns a new psycopg2 connection using environment variables.
    """
    return psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT,
        dbname=PG_DBNAME,
        user=PG_USER,
        password=PG_PASSWORD,
    )


# ---------- SERVICE DESCRIPTION ----------

def load_service_description(project_id):
    """
    Load the latest service_description row for a given project_id.

    Returns a dict like:
    {
        "summary": "...",
        "detailed_description": "...",
        "target_audience": "...",
        "niche": "...",
        "price_range": "...",
        "location_type": "...",
        "key_benefits": [...],
        "constraints": [...]
    }
    or {} if not found.
    """
    query = """
        SELECT
            summary,
            detailed_description,
            target_audience,
            niche,
            price_range,
            location_type,
            key_benefits,
            constraints
        FROM service_description
        WHERE project_id = %s
        ORDER BY created_at DESC
        LIMIT 1;
    """

    with _get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, (project_id,))
            row = cur.fetchone()

    if not row:
        logging.warning(f"No service_description found for project_id={project_id}")
        return {}

    # RealDictCursor already gives us a dict, but we can convert to a plain dict
    return {
        "summary": row.get("summary"),
        "detailed_description": row.get("detailed_description"),
        "target_audience": row.get("target_audience"),
        "niche": row.get("niche"),
        "price_range": row.get("price_range"),
        "location_type": row.get("location_type"),
        "key_benefits": row.get("key_benefits") or [],
        "constraints": row.get("constraints") or [],
    }


# ---------- APP USER HELPERS ----------

def save_app_user(
    full_name: str,
    timezone: str | None = None,
    locale: str | None = None,
):
    """
    Insert a new app_user row and return its id.

    For this MVP:
    - We don't use email.
    - We just create a new row every time.
    """

    if not full_name:
        raise ValueError("full_name is required to save_app_user")

    query = """
        INSERT INTO app_user (full_name, timezone, locale)
        VALUES (%s, %s, %s)
        RETURNING id;
    """

    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (full_name, timezone, locale))
            (app_user_id,) = cur.fetchone()
        conn.commit()

    logging.info(
        f"Saved app_user id={app_user_id} full_name={full_name} timezone={timezone} locale={locale}"
    )
    return app_user_id


# ---------- LLM: BRAND IDENTITY GENERATION ----------

def generate_brand_identity(service_desc, answers, model: str = "gpt-4.1-mini-2025-04-14"):
    """
    Call an LLM (OpenAI) to generate a BrandIdentityMap.

    - service_desc: dict from load_service_description(...)
    - answers: dict collected by BrandingInteractiveAgent (service_summary, values, etc.)

    Returns a Python dict with keys like:
    - brand_name
    - tagline
    - mission
    - values (list)
    - uniqueValueProposition
    - toneOfVoice
    - audiencePersonas
    - visualDirection
    - brandStory
    """

    client = OpenAI()  # uses OPENAI_API_KEY from env

    prompt = BRANDING_FINAL_PROMPT.format(
        service_description=json.dumps(service_desc or {}, indent=2),
        answers_json=json.dumps(answers or {}, indent=2),
    )

    messages = [
        {
            "role": "system",
            "content": "You are a senior brand strategist. Always respond with valid JSON only.",
        },
        {"role": "user", "content": prompt},
    ]

    logging.info("Calling OpenAI to generate BrandIdentityMap...")
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.3,
        max_tokens=1200,
    )

    content = resp.choices[0].message.content.strip()
    logging.debug(f"Raw LLM response for BrandIdentityMap: {content}")

    # Parse JSON safely
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # Try a very naive JSON extraction if the model added extra text
        try:
            first = content.find("{")
            last = content.rfind("}")
            if first != -1 and last != -1 and last > first:
                json_str = content[first : last + 1]
                return json.loads(json_str)
        except Exception:
            pass

        logging.error("Failed to parse BrandIdentityMap JSON from LLM response.")
        raise


# ---------- BRAND IDENTITY PERSISTENCE ----------

def save_brand_identity(project_id, brand_identity: dict):
    """
    Insert a new brand_identity row using the MVP schema.
    - Computes version = max(version) + 1 for that project_id.
    - Marks previous is_current = FALSE.
    - Inserts new row with is_current = TRUE.
    """

    if not project_id:
        raise ValueError("project_id is required to save_brand_identity")

    # Required fields we expect from the LLM
    brand_name = brand_identity.get("brand_name")
    mission = brand_identity.get("mission")
    if not brand_name or not mission:
        raise ValueError("brand_identity must contain at least 'brand_name' and 'mission'")

    tagline = brand_identity.get("tagline")
    values = brand_identity.get("values") or []

    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            # Compute next version number
            cur.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 FROM brand_identity WHERE project_id = %s;",
                (project_id,),
            )
            (next_version,) = cur.fetchone()

            # Mark existing current version as not current
            cur.execute(
                "UPDATE brand_identity SET is_current = FALSE WHERE project_id = %s AND is_current = TRUE;",
                (project_id,),
            )

            # Insert new brand_identity
            cur.execute(
                """
                INSERT INTO brand_identity (
                    project_id,
                    version,
                    is_current,
                    brand_name,
                    tagline,
                    mission,
                    values,
                    data
                )
                VALUES (%s, %s, TRUE, %s, %s, %s, %s, %s::jsonb);
                """,
                (
                    project_id,
                    next_version,
                    brand_name,
                    tagline,
                    mission,
                    values,
                    json.dumps(brand_identity),
                ),
            )

        conn.commit()

    logging.info(
        f"Saved BrandIdentityMap for project_id={project_id} as version={next_version}"
    )
    return next_version
