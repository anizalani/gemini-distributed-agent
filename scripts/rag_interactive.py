import argparse
import os
import psycopg2
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
import sys
import subprocess
import json

print("DEBUG: This is rag_interactive.py version 20250903.1")

def call_gemini_api(prompt, model_name):
    script_dir = os.path.dirname(__file__)
    project_root = os.path.abspath(os.path.join(script_dir, '..'))
    gemini_cli_path = os.path.join(project_root, 'node_modules', '.bin', 'gemini')

    command = [gemini_cli_path, '--model', model_name, '--prompt', prompt]
    print(f"DEBUG (call_gemini_api): Executing command: {' '.join(command)}") # Add this line
    try:
        # Pass the current environment to the subprocess
        result = subprocess.run(command, capture_output=True, text=True, check=True, env=os.environ)
        return result.stdout
    except subprocess.CalledProcessError as e:
        error_message = f"Error from Gemini CLI: {e.stderr.strip()}"
        print(error_message)  # Log the error to the console/log file
        return error_message  # Return the error as a string to be displayed to the user

def main():
    parser = argparse.ArgumentParser(description="Run RAG interactive session.")
    parser.add_argument("--model", type=str, required=True, help="Gemini model to use.")
    parser.add_argument("--session-id", type=str, help="Session ID for the interactive session.")
    args = parser.parse_args()

    print(f"Starting RAG interactive session with model: {args.model}")

    # Load environment variables
    # Load environment variables from CODE_DIR, which is set by gembot.sh
    code_dir = os.getenv("CODE_DIR", os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    # Load environment variables from CODE_DIR, which is set by gembot.sh
    code_dir = os.getenv("CODE_DIR", os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    print(f"DEBUG (rag_interactive.py): CODE_DIR is {code_dir}")
    env_file_path = os.path.join(code_dir, '.env')
    postgres_env_file_path = os.path.join(code_dir, '.postgres.env')
    print(f"DEBUG (rag_interactive.py): Attempting to load .env from {env_file_path}")
    print(f"DEBUG (rag_interactive.py): Attempting to load .postgres.env from {postgres_env_file_path}")
    load_dotenv(env_file_path, override=True)
    load_dotenv(postgres_env_file_path, override=True)

    # Database connection
    conn = None
    try:
        # Explicitly get PGPASSWORD after loading dotenv files
        pg_password = os.getenv("PGPASSWORD")
        print(f"DEBUG (rag_interactive.py): PGPASSWORD after load_dotenv (masked): {pg_password[:4]}...{pg_password[-4:]}" if pg_password else "DEBUG (rag_interactive.py): PGPASSWORD after load_dotenv is not set.")

        # Ensure PGPASSWORD is set in the environment for psycopg2
        if pg_password:
            os.environ["PGPASSWORD"] = pg_password

        conn = psycopg2.connect(
            host=os.getenv("POSTGRES_HOST"),
            port=os.getenv("POSTGRES_PORT"),
            database=os.getenv("POSTGRES_DB"),
            user=os.getenv("POSTGRES_USER"),
            password=pg_password
        )
        print("Successfully connected to the PostgreSQL database.")
        cursor = conn.cursor()
        cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        conn.commit()

        # Create documents table if it doesn't exist
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id SERIAL PRIMARY KEY,
                content TEXT NOT NULL,
                embedding VECTOR(384) NOT NULL,
                source_documents JSONB,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
        """)
        # Add new columns if they don't exist
        cursor.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS gemini_model TEXT;")
        cursor.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS gemini_output TEXT;")
        
        
        cursor.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS token_count INTEGER;")
        conn.commit()
        cursor.close()
    except Exception as e:
        print(f"Error connecting to database: {e}")
        return

    # Load embedding model
    try:
        embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        print("Successfully loaded SentenceTransformer model.")
    except Exception as e:
        print(f"Error loading SentenceTransformer model: {e}")
        if conn:
            conn.close()
        return

    print("\n--- RAG Interactive Session ---")
    print("Type 'quit' or 'exit' to end the session.")

    request_pipe_path = f"/tmp/{args.session_id}.req"
    response_pipe_path = f"/tmp/{args.session_id}.res"

    # Open pipes outside the loop to keep them alive
    try:
        f_res = open(response_pipe_path, 'w')
        f_req = open(request_pipe_path, 'r')
    except FileNotFoundError as e:
        print(f"Error opening named pipes: {e}. Exiting.")
        if conn:
            conn.close()
        return

    while True:
        user_query = f_req.readline().strip()

        if user_query.lower() in ["quit", "exit"]:
            break

        # 1. Embed the user_query
        query_embedding = embedding_model.encode(user_query).tolist()

        

        # 2. Search the vector database for relevant documents
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, content FROM documents
            ORDER BY embedding <-> %s
            LIMIT 3;
            """, (str(query_embedding),))
        retrieved_docs = cursor.fetchall()
        cursor.close()

        source_doc_ids = []
        context_contents = []
        if retrieved_docs:
            for doc_id, doc_content in retrieved_docs:
                source_doc_ids.append(doc_id)
                context_contents.append(doc_content)
            context = "\n\nRelevant Context:\n" + "\n---\n".join(context_contents)
        else:
            context = ""

        print(f"DEBUG (rag_interactive.py - pre-insert): source_doc_ids={source_doc_ids}")
        print(f"DEBUG (rag_interactive.py - pre-insert): json_dumped_source_doc_ids={json.dumps(source_doc_ids)}")

        # Store the user query, Gemini response, and RAG context in the database
        try:
            cursor = conn.cursor()
            print(f"DEBUG (rag_interactive.py - insert): user_query={user_query[:50]}...")
            print(f"DEBUG (rag_interactive.py - insert): query_embedding={str(query_embedding)[:50]}...")
            print(f"DEBUG (rag_interactive.py - insert): args.model={args.model}")
            print(f"DEBUG (rag_interactive.py - insert): gemini_response={gemini_response[:50]}...")
            print(f"DEBUG (rag_interactive.py - insert): source_documents_to_insert={json.dumps(source_doc_ids)[:50]}...")
            print(f"DEBUG (rag_interactive.py - insert): token_count=0")
            cursor.execute("""
                INSERT INTO documents (content, embedding, gemini_model, gemini_output, source_documents)
                VALUES (%s, %s, %s, %s, %s);
                """, (user_query, str(query_embedding), args.model, gemini_response, json.dumps(source_doc_ids)))
            conn.commit()
            cursor.close()
        except Exception as e:
            print(f"Error inserting document into database: {e}")
            conn.rollback()

        # 3. Construct a prompt for the Gemini model
        full_prompt = f"{user_query}"

        # 4. Call the Gemini API with the constructed prompt
        gemini_response = call_gemini_api(full_prompt, args.model)

        

        f_res.write(gemini_response + "\n")
        f_res.flush() # Ensure the response is written immediately

    f_req.close()
    f_res.close()
    if conn:
        conn.close()
    print("RAG interactive session ended.")

if __name__ == "__main__":
    main()
