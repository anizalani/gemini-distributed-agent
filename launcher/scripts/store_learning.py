

import os
import sys
import psycopg2
import json

def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("PGHOST", "localhost"),
        port=os.getenv("PGPORT", "5432"),
        database=os.getenv("PGDATABASE", "gemini_agents"),
        user=os.getenv("PGUSER", "gemini_user"),
        password=os.getenv("PGPASSWORD", "")
    )

def store_learning(
    learning_text,
    title=None,
    topic="general",
    tags=None,
    summary=None,
    source_type="user_input",
    source_identifier="cli_session",
    source_details=None,
    author="cli_user",
    llm_model_used=None
):
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Default title and summary if not provided
        if not title:
            title = learning_text.split('\n')[0][:100] + "..." if len(learning_text) > 100 else learning_text
        if not summary:
            summary = learning_text[:200] + "..." if len(learning_text) > 200 else learning_text

        # Convert tags to PostgreSQL array literal
        tags_array_literal = '{}'
        if tags:
            if isinstance(tags, list):
                tags_array_literal = '{' + ','.join([f'"{'{' + tag.replace('"', "''") + '}"}' for tag in tags]) + '}'
            elif isinstance(tags, str):
                tags_array_literal = '{' + ','.join([f'"{'{' + t.strip().replace('"', "''") + '}"}' for t in tags.split(',')]) + '}'

        # Insert into learnings table (current version)
        cur.execute(
            """INSERT INTO learnings (
                title, topic, tags, learning_text, summary,
                source_type, source_identifier, source_details, author, llm_model_used
            ) VALUES (%s, %s, %s::TEXT[], %s, %s, %s, %s, %s, %s, %s) RETURNING id;""",
            (
                title, topic, tags_array_literal, learning_text, summary,
                source_type, source_identifier, json.dumps(source_details) if source_details else None, author, llm_model_used
            )
        )
        learning_id = cur.fetchone()[0]

        # Insert into learnings_versions table (first version)
        cur.execute(
            """INSERT INTO learnings_versions (
                learning_id, version_number, title_content, topic_content, tags_content,
                learning_text_content, summary_content, source_type_content, source_identifier_content,
                source_details_content, modified_by, llm_model_used_content
            ) VALUES (%s, %s, %s, %s, %s::TEXT[], %s, %s, %s, %s, %s, %s, %s) RETURNING version_id;""",
            (
                learning_id, 1, title, topic, tags_array_literal,
                learning_text, summary, source_type, source_identifier,
                json.dumps(source_details) if source_details else None, author, llm_model_used
            )
        )
        version_id = cur.fetchone()[0]

        # Update learnings.current_version_id
        cur.execute(
            "UPDATE learnings SET current_version_id = %s WHERE id = %s;",
            (version_id, learning_id)
        )

        conn.commit()
        print(f"Learning '{title}' (ID: {learning_id}) successfully stored with version {version_id}.")

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"Error storing learning: {e}", file=sys.stderr)
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

if __name__ == "__main__":
    # Example usage from CLI:
    # python store_learning.py "This is a new learning about RAG." --title "RAG Intro" --topic "RAG" --tags "RAG,LLM"
    
    # Parse arguments for more flexibility
    args = sys.argv[1:]
    learning_text_arg = None
    kwargs = {}

    i = 0
    while i < len(args):
        arg = args[i]
        if arg.startswith("--"):
            key = arg[2:].replace("-", "_")
            if i + 1 < len(args) and not args[i+1].startswith("--"):
                value = args[i+1]
                if key == "tags": # Handle tags as a comma-separated string
                    kwargs[key] = value.split(',')
                elif key == "source_details": # Handle source_details as JSON string
                    try:
                        kwargs[key] = json.loads(value)
                    except json.JSONDecodeError:
                        print(f"Warning: Invalid JSON for --source-details: {value}", file=sys.stderr)
                        kwargs[key] = None
                else:
                    kwargs[key] = value
                i += 1
            else:
                kwargs[key] = True # For boolean flags if any
        else:
            if learning_text_arg is None:
                learning_text_arg = arg
            else:
                print(f"Warning: Ignoring extra positional argument: {arg}", file=sys.stderr)
        i += 1

    if learning_text_arg is None:
        print("Usage: python store_learning.py \"<learning_text>\" [--title <title>] [--topic <topic>] [--tags <tag1,tag2>] [--summary <summary>] [--source-type <type>] [--source-identifier <id>] [--source-details <json>] [--author <author>] [--llm-model-used <model>]")
        sys.exit(1)
    
    store_learning(learning_text_arg, **kwargs)
