import db_utils
import time
import logging
import subprocess
import json
import sys
import os

import os
from dotenv import load_dotenv

# --- Configuration ---
# Load environment variables
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path=dotenv_path)

PROJECT_ROOT = os.getenv("PROJECT_ROOT", ".")
LOG_FILE = os.path.join(PROJECT_ROOT, "agent.log")
KEY_EXHAUSTED_SLEEP_MINUTES = 5

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)

def run_gemini_command(api_key, prompt, context):
    """
    Runs the Gemini CLI with the provided API key and prompt.
    Returns the response and token count.
    """
    logging.info(f"Executing Gemini command with key ending in '...{api_key[-4:]}'")
    
    cmd = ["gemini"]
    
    try:
        # Set the API key in the environment for the subprocess
        env = os.environ.copy()
        env["GEMINI_API_KEY"] = api_key
        
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            check=True, 
            env=env,
            input=prompt
        )
        
        response = result.stdout.strip()
        token_count = len(prompt.split()) + len(response.split())

        logging.info(f"Gemini command successful. Response: {response}, Token usage: {token_count}")
        return response, token_count

    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        logging.error(f"Gemini command failed: {e.stderr}")
        return None, 0
    except json.JSONDecodeError as e:
        logging.error(f"Failed to decode Gemini CLI JSON output: {e}")
        return result.stdout.strip(), 0

import sys

def main():
    """Main function for the interactive Gemini agent."""
    if len(sys.argv) < 2:
        print("Usage: python gemini_agent.py <prompt>")
        return

    prompt = " ".join(sys.argv[1:])
    
    db_utils.send_slack_notification(f"Agent starting up for prompt: {prompt}", level="info")
    logging.info(f"Agent starting up for prompt: {prompt}")
    conn = db_utils.get_db_connection()
    if not conn:
        db_utils.send_slack_notification("Agent failed to connect to the database.", level="error")
        return

    try:
        with conn.cursor() as cur:
            task_id = db_utils.get_task_id()
            context = db_utils.get_or_create_task(cur, task_id)
            
            key_info = db_utils.get_available_key(cur)
            
            if not key_info:
                message = "No available API keys. Sleeping for {} minutes.".format(KEY_EXHAUSTED_SLEEP_MINUTES)
                db_utils.send_slack_notification(message, level="warning")
                logging.warning(message)
                time.sleep(KEY_EXHAUSTED_SLEEP_MINUTES * 60)
                return

            key_name, api_key = key_info
            logging.info(f"Selected API key: {key_name}")

            db_utils.throttle_if_needed(cur, key_name)

            response, token_count = run_gemini_command(api_key, prompt, context)

            if response and token_count > 0:
                context['history'].append({'prompt': prompt, 'response': response})
                db_utils.update_key_and_log_usage(cur, key_name, task_id, token_count, "non_interactive_request")
                db_utils.update_task_context(cur, task_id, context)
                db_utils.send_slack_notification(f"Interactive task '{task_id}' completed. Used key '{key_name}' ({token_count} tokens).")
                print(f"\nResponse: {response}\n")

            conn.commit()

    except Exception as e:
        error_message = f"An unexpected error occurred: {e}"
        db_utils.send_slack_notification(error_message, level="error")
        logging.error(error_message, exc_info=True)
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()
            logging.info("Database connection closed.")
    
    logging.info("Agent shutting down.")

if __name__ == "__main__":
    main()
