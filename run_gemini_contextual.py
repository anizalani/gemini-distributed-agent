

import db_utils
import logging
import subprocess
import json
import sys
import os

# --- Configuration ---
LOG_FILE = "/home/ubuntu/gemini-distributed-agent/agent.log"
# IMPORTANT: This should point to the base Gemini CLI executable
GEMINI_CLI_COMMAND = "/usr/local/bin/gemini" 

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)

def run_actual_gemini_command(api_key, prompt, context_file):
    """
    Runs the actual Gemini CLI command with the provided API key, prompt, and context file.
    """
    logging.info(f"Executing Gemini command with key ending in '...{api_key[-4:]}'")
    
    env = os.environ.copy()
    env['GEMINI_API_KEY'] = api_key
    
    cmd = [
        GEMINI_CLI_COMMAND,
        "--prompt", prompt,
        "--context-file", context_file,
        "--json-output" # Assuming the CLI can output JSON for parsing
    ]
    
    try:
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            check=True,
            env=env
        )
        output = json.loads(result.stdout)
        token_count = output.get("usage", {}).get("total_tokens", 0)
        response_text = output.get("response", "")
        logging.info(f"Gemini command successful. Token usage: {token_count}")
        return response_text, token_count
    except FileNotFoundError:
        logging.error(f"CRITICAL: The command '{GEMINI_CLI_COMMAND}' was not found.")
        logging.error("Please update the GEMINI_CLI_COMMAND variable in this script.")
        return None, 0
    except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
        logging.error(f"Gemini command failed: {e}")
        logging.error(f"Stderr: {e.stderr if hasattr(e, 'stderr') else 'N/A'}")
        return None, 0

def main():
    """Main function for the interactive Gemini script."""
    if len(sys.argv) < 2:
        print("Usage: python3 run_gemini_contextual.py \"<your prompt>\" [task_id]")
        sys.exit(1)

    prompt = sys.argv[1]
    task_id = sys.argv[2] if len(sys.argv) > 2 else db_utils.get_task_id()

    logging.info(f"Starting interactive run for task '{task_id}'.")
    
    conn = db_utils.get_db_connection()
    if not conn:
        db_utils.send_slack_notification(f"Interactive run for task '{task_id}' failed to connect to the database.", level="error")
        return

    try:
        with conn.cursor() as cur:
            # Get an API key
            key_info = db_utils.get_available_key(cur)
            if not key_info:
                message = f"No available API keys for interactive task '{task_id}'."
                db_utils.send_slack_notification(message, level="error")
                logging.error(message)
                return

            key_name, api_key = key_info
            logging.info(f"Selected API key: {key_name}")

            # Throttle if necessary
            db_utils.throttle_if_needed(cur, key_name)

            # Get context and write to a temporary file
            context = db_utils.get_or_create_task(cur, task_id)
            context_file_path = f"/tmp/{task_id}_context.json"
            with open(context_file_path, 'w') as f:
                json.dump(context, f)

            # Run the command
            response_text, token_count = run_actual_gemini_command(api_key, prompt, context_file_path)

            # If successful, update everything
            if response_text is not None:
                print("--- Gemini Response ---")
                print(response_text)
                print("-----------------------")

                # Update context
                context['history'].append({'role': 'user', 'parts': [{'text': prompt}]})
                context['history'].append({'role': 'model', 'parts': [{'text': response_text}]})
                db_utils.update_task_context(cur, task_id, context)

                # Update usage logs
                db_utils.update_key_and_log_usage(cur, key_name, task_id, token_count, "interactive_request")
            else:
                db_utils.send_slack_notification(f"Gemini command failed for task '{task_id}' using key '{key_name}'. Check logs.", level="error")

            conn.commit()
            logging.info(f"Interactive run for task '{task_id}' finished.")

    except Exception as e:
        error_message = f"An unexpected error occurred during interactive run for task '{task_id}': {e}"
        db_utils.send_slack_notification(error_message, level="error")
        logging.error(error_message, exc_info=True)
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    main()

