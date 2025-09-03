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

def retrieve_learnings(prompt, limit=5):
    learnings = []
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        search_terms = prompt.split()
        if not search_terms:
            return []

        # Constructing a query that searches for any of the terms in title, summary, or learning_text
        # Using ILIKE for case-insensitive substring matching
        query_parts = []
        query_params = []
        for term in search_terms:
            query_parts.append("title ILIKE %s OR summary ILIKE %s OR learning_text ILIKE %s")
            query_params.extend([f"%{term}%", f"%{term}%", f"%{term}%"])
        
        # Also search in tags array
        tags_query_parts = [f"%s = ANY(tags)" for _ in search_terms]
        tags_query_params = [term for term in search_terms]

        # Combine all search conditions
        full_query = f"SELECT title, summary, learning_text, topic, tags, source_type, source_identifier, llm_model_used FROM learnings WHERE ({' OR '.join(query_parts)}) OR ({' OR '.join(tags_query_parts)}) ORDER BY updated_at DESC LIMIT %s;"
        full_params = query_params + tags_query_params + [limit]

        cur.execute(full_query, full_params)
        
        for row in cur.fetchall():
            title, summary, learning_text, topic, tags, source_type, source_identifier, llm_model_used = row
            learnings.append({
                "title": title,
                "summary": summary,
                "learning_text": learning_text, # Can choose to send full text or just summary to LLM
                "topic": topic,
                "tags": tags,
                "source_type": source_type,
                "source_identifier": source_identifier,
                "llm_model_used": llm_model_used
            })
        
    except Exception as e:
        print(f"Error retrieving learnings: {e}", file=sys.stderr)
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
    
    return learnings

if __name__ == "__main__":
    if len(sys.argv) < 2:
        # If no prompt is provided, return nothing
        sys.exit(0)
    
    user_prompt = sys.argv[1]
    retrieved = retrieve_learnings(user_prompt)
    
    if retrieved:
        print("--- Retrieved Learnings ---")
        for learning in retrieved:
            # For CLI output, print a concise version. The shell script will format for LLM.
            print(f"Title: {learning['title']}")
            print(f"Summary: {learning['summary']}")
            print(f"Topic: {learning['topic']}")
            if learning['tags']:
                print(f"Tags: {', '.join(learning['tags'])}")
            print(f"Source Type: {learning['source_type']}")
            if learning['source_identifier']:
                print(f"Source ID: {learning['source_identifier']}")
            if learning['llm_model_used']:
                print(f"LLM Model: {learning['llm_model_used']}")
            print("-------------------------")
    else:
        print("") # Print an empty line if no learnings to avoid extra output