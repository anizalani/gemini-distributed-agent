import argparse
import os
import psycopg2
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
import sys
import subprocess
import json
import select
import re

print("DEBUG: This is rag_interactive.py version 20250903.1")

def execute_shell_command(command):
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        return result.stdout + result.stderr
    except Exception as e:
        return str(e)

def read_file_content(file_path):
    try:
        with open(file_path, 'r') as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {e}"

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
    parser.add_argument("--log-file", type=str, help="Path to the log file.")
    args = parser.parse_args()

    # Redirect stdout and stderr to the log file if provided
    if args.log_file:
        try:
            log_f = open(args.log_file, 'w')
            sys.stdout = log_f
            sys.stderr = log_f
        except Exception as e:
            # If we can't open the log file, we can't log the error. Print to original stderr and exit.
            print(f"Fatal: Could not open log file {args.log_file}. Error: {e}", file=sys.__stderr__)
            exit(1)

    print(f"Starting RAG interactive session with model: {args.model}")

    # Load environment variables
    # Load environment variables from CODE_DIR, which is set by gembot.sh
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
        pg_password = os.getenv("POSTGRES_PASSWORD")
        print(f"DEBUG (rag_interactive.py): POSTGRES_PASSWORD after load_dotenv (masked): {pg_password[:4]}...{pg_password[-4:]}" if pg_password else "DEBUG (rag_interactive.py): POSTGRES_PASSWORD after load_dotenv is not set.")

        # Ensure PGPASSWORD is set in the environment for psycopg2
        if pg_password:
            os.environ["PGPASSWORD"] = pg_password

        conn_string = f"dbname='{os.getenv('POSTGRES_DB')}' user='{os.getenv('POSTGRES_USER')}' host='{os.getenv('POSTGRES_HOST')}' password='{os.getenv('POSTGRES_PASSWORD')}' connect_timeout=10"
        conn = psycopg2.connect(conn_string)
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
        cursor.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS executed_command_output TEXT;")
        
        
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
        print("DEBUG: Waiting for user input...")
        # Use select for a timeout on the read operation
        ready_to_read, _, _ = select.select([f_req], [], [], 60)
        if not ready_to_read:
            print("Timeout waiting for user input. Exiting.")
            break

        user_query = f_req.readline().strip()
        print(f"DEBUG: Received user query: {user_query}")

        if not user_query:
            break

        if user_query.lower() in ["quit", "exit"]:
            break

        # --- File Content Injection ---
        file_path_match = re.search(r'(/["\w/.-]+)', user_query)
        file_content = ""
        if file_path_match:
            file_path = file_path_match.group(1)
            print(f"DEBUG: Found file path in query: {file_path}")
            if os.path.isdir(file_path):
                workplan_path = os.path.join(file_path, "workplan.md")
                if os.path.exists(workplan_path):
                    file_content = read_file_content(workplan_path)
                    print(f"DEBUG: Read file content from workplan.md (first 100 chars): {file_content[:100]}")
                else:
                    file_content = f"Directory found, but no workplan.md inside: {file_path}"
            elif os.path.exists(file_path):
                file_content = read_file_content(file_path)
                print(f"DEBUG: Read file content (first 100 chars): {file_content[:100]}")
            else:
                file_content = f"File not found: {file_path}"
                print(f"DEBUG: {file_content}")

        # --- DIAGNOSTIC OVERRIDE ---
        # This block will run once to diagnose the execution environment. 
        # f_res.write("Running diagnostics...\n") 
        # f_res.flush() 
        # diagnostic_command = "echo '--- DIAGNOSTICS ---'; echo 'User:'; whoami; echo 'PWD:'; pwd; echo 'Listing /:'; ls -l /; echo 'Listing /srv:'; ls -l /srv; echo 'Listing workspace /srv:'; ls -l /home/ubuntu/gemini_workspace/srv; echo '--- END DIAGNOSTICS ---"
        # command_output = execute_shell_command(diagnostic_command) 
        # f_res.write(command_output + "\n") 
        # f_res.flush() 
        # break # End after the diagnostic

        # --- DIAGNOSTIC OVERRIDE --- 
        # This block will run once to diagnose the execution environment. 
        # f_res.write("Running diagnostics...\n") 
        # f_res.flush() 
        # diagnostic_command = "echo '--- DIAGNOSTICS ---'; echo 'User:'; whoami; echo 'PWD:'; pwd; echo 'Listing /:'; ls -l /; echo 'Listing /srv:'; ls -l /srv; echo 'Listing workspace /srv:'; ls -l /home/ubuntu/gemini_workspace/srv; echo '--- END DIAGNOSTICS ---" 
        # command_output = execute_shell_command(diagnostic_command) 
        # f_res.write(command_output + "\n") 
        # f_res.flush() 
        # break # End after the diagnostic

        # 1. Embed the user_query
        query_embedding = embedding_model.encode(user_query).tolist()

        # Insert the user query into the database and get the ID
        doc_id = None
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO documents (content, embedding, gemini_model)
                VALUES (%s, %s, %s) RETURNING id;
                """, (user_query, str(query_embedding), args.model))
            doc_id = cursor.fetchone()[0]
            conn.commit()
            cursor.close()
            print(f"DEBUG: Inserted user query with doc_id: {doc_id}")
        except Exception as e:
            print(f"Error inserting user query into database: {e}")
            conn.rollback()

        # 2. Search the vector database for relevant documents
        context = ""
        source_doc_ids = []
        try:
            cursor = conn.cursor()
            # The <-> operator calculates the cosine distance between the query embedding and the stored embeddings
            cursor.execute("""
                SELECT id, content, gemini_output, executed_command_output FROM documents
                WHERE id != %s AND embedding <-> %s < 0.6
                ORDER BY embedding <-> %s
                LIMIT 3;
                """, (doc_id, str(query_embedding), str(query_embedding)))
            
            results = cursor.fetchall()
            if results:
                context += "Relevant past conversations:\n"
                for r_id, r_content, r_gemini_output, r_executed_command_output in results:
                    context += f"- User query: {r_content}\n"
                    if r_gemini_output:
                        context += f"  - Gemini response: {r_gemini_output}\n"
                    if r_executed_command_output:
                        context += f"  - Executed command output: {r_executed_command_output}\n"
                    source_doc_ids.append(r_id)
            
            cursor.close()
            print(f"DEBUG: Retrieved context from {len(results)} documents.")
        except Exception as e:
            print(f"Error searching for similar documents: {e}")
            conn.rollback()

        print(f"DEBUG (rag_interactive.py - pre-insert): source_doc_ids={source_doc_ids}")
        print(f"DEBUG (rag_interactive.py - pre-insert): json_dumped_source_doc_ids={json.dumps(source_doc_ids)}")

        # 3. Construct a prompt for the Gemini model
        full_prompt = agentic_prompt = f"""You are a helpful AI assistant with the ability to execute shell commands.
When you need to execute a command, you MUST respond with ONLY the JSON object and no other text.
The JSON object should have a single key, "execute_shell", with the value being another JSON object containing a "command" key and the command to execute as its value.

For example, if the user asks to list files, you would respond with nothing but the following JSON:
{{"execute_shell": {{"command": "ls -l"}}}}

Now, please respond to the following user query:
{user_query}
"""
        if context:
            full_prompt += f"""Here is some relevant context from past conversations:
---
{context}
---
"""

        if file_content:
            full_prompt += f"""
The user has also provided the following file content for context:
---
{file_content}
---
"""

        # 4. Call the Gemini API with the constructed prompt
        print("DEBUG: Calling Gemini API...")
        gemini_response = call_gemini_api(full_prompt, args.model)
        print(f"DEBUG: Received Gemini response: {gemini_response}")

        # 5. Parse the Gemini API's response for shell commands
        print("DEBUG: Parsing Gemini response for shell commands...")
        decoder = json.JSONDecoder()
        pos = 0
        while pos < len(gemini_response):
            try:
                response_json, pos = decoder.raw_decode(gemini_response, pos)
                if "execute_shell" in response_json:
                    command_to_execute = response_json["execute_shell"]["command"]
                    
                    # Prompt for user confirmation
                    print(f"DEBUG: Requesting user confirmation for command: {command_to_execute}")
                    f_res.write(f"USER_CONFIRMATION_REQUEST: Gemini wants to execute the following command: {command_to_execute}\n")
                    f_res.flush()
                    
                    # Read the user's confirmation from the request pipe
                    print("DEBUG: Waiting for user confirmation...")
                    ready_to_read, _, _ = select.select([f_req], [], [], 60)
                    if not ready_to_read:
                        print("Timeout waiting for user confirmation. Exiting.")
                        break
                    user_confirmation = f_req.readline().strip()
                    print(f"DEBUG: Received user confirmation: {user_confirmation}")

                    if user_confirmation.lower() == "y":
                        print(f"DEBUG: Executing command: {command_to_execute}")
                        command_output = execute_shell_command(command_to_execute)
                        print(f"DEBUG: Command output: {command_output}")
                        
                        # Store the direct output
                        try:
                            cursor = conn.cursor()
                            cursor.execute("UPDATE documents SET executed_command_output = %s WHERE id = %s;", (command_output, doc_id))
                            conn.commit()
                            cursor.close()
                        except Exception as e:
                            print(f"Error updating executed_command_output: {e}")
                            conn.rollback()

                        # Feedback loop to the model for a conversational response
                        feedback_prompt = f"The command '{command_to_execute}' was executed and the output was: {command_output}. Please summarize this output and present it to the user in a helpful and readable format."
                        print("DEBUG: Sending feedback to Gemini API...")
                        gemini_response = call_gemini_api(feedback_prompt, args.model)
                        print(f"DEBUG: Received feedback response: {gemini_response}")
                    else:
                        gemini_response = "Command execution cancelled by user."
            except json.JSONDecodeError:
                # The extracted string wasn't valid JSON, so we just pass
                pos += 1

        # Store the Gemini response and RAG context in the database
        if doc_id:
            try:
                cursor = conn.cursor()
                print(f"DEBUG (rag_interactive.py - update): doc_id={doc_id}")
                print(f"DEBUG (rag_interactive.py - update): gemini_response={gemini_response[:50]}...")
                print(f"DEBUG (rag_interactive.py - update): source_documents_to_insert={json.dumps(source_doc_ids)[:50]}...")
                cursor.execute("""
                    UPDATE documents
                    SET gemini_output = %s, source_documents = %s
                    WHERE id = %s;
                    """, (gemini_response, json.dumps(source_doc_ids), doc_id))
                conn.commit()
                cursor.close()
            except Exception as e:
                print(f"Error updating document in database: {e}")
                conn.rollback()

        

        try:
            if not f_res.closed:
                f_res.write(gemini_response + "\n")
                f_res.flush() # Ensure the response is written immediately
            else:
                print("DEBUG: Response pipe is closed, skipping write.")
        except BrokenPipeError:
            print("DEBUG: Broken pipe error, exiting gracefully.")
            break

    try:
        if not f_req.closed:
            f_req.close()
        if not f_res.closed:
            f_res.close()
    except BrokenPipeError:
        print("DEBUG: Broken pipe error while closing pipes, ignoring.")
    if conn:
        conn.close()
    print("RAG interactive session ended.")

if __name__ == "__main__":
    main()