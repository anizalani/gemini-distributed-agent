
import psycopg2
import logging
import json
import datetime
import socket
import os
import time
from dotenv import load_dotenv

# --- Configuration ---
# Load the main .env file from the project root
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path=dotenv_path)

# Load the PostgreSQL credentials from the path specified in the main .env file
postgres_env_path = os.getenv("POSTGRES_ENV_FILE")
if postgres_env_path:
    load_dotenv(dotenv_path=postgres_env_path)
else:
    logging.error("POSTGRES_ENV_FILE not set in .env")
    # Consider exiting or handling this error appropriately
    
DB_NAME = "gemini_distributed_agent"
DB_USER = os.getenv("POSTGRES_USER")
DB_PASS = os.getenv("POSTGRES_PASSWORD")
DB_HOST = "localhost"
DB_PORT = "5432"
MIN_REQUEST_INTERVAL_SECONDS = 30

def get_db_connection():
    """Establishes a connection to the PostgreSQL database."""
    try:
        conn = psycopg2.connect(
            dbname=DB_NAME, user=DB_USER, password=DB_PASS, host=DB_HOST, port=DB_PORT
        )
        return conn
    except psycopg2.OperationalError as e:
        logging.error(f"Database connection failed: {e}")
        return None

def get_task_id():
    """Generates a unique task ID from the hostname and current date."""
    hostname = socket.gethostname()
    today = datetime.date.today().strftime('%Y-%m-%d')
    return f"{hostname}-{today}"

def get_or_create_task(cur, task_id):
    """Fetches a task by ID or creates a new one if it doesn't exist."""
    cur.execute("SELECT context FROM tasks WHERE id = %s;", (task_id,))
    task = cur.fetchone()
    if task:
        logging.info(f"Resuming existing task: {task_id}")
        return json.loads(task[0]) if isinstance(task[0], str) else task[0]
    else:
        logging.info(f"Creating new task: {task_id}")
        context = {'history': []}
        cur.execute(
            "INSERT INTO tasks (id, context, status) VALUES (%s, %s, %s);",
            (task_id, json.dumps(context), 'active')
        )
        return context

def get_available_key(cur):
    """Retrieves an available API key."""
    cur.execute("""
        SELECT key_name, key_value
        FROM api_keys
        WHERE (quota_exhausted = FALSE OR quota_exhausted IS NULL)
          AND (disabled_until IS NULL OR disabled_until < NOW())
          AND daily_request_count < 60
        ORDER BY last_used ASC NULLS FIRST
        LIMIT 1;
    """)
    return cur.fetchone()

def throttle_if_needed(cur, key_name):
    """Sleeps if the key was used too recently to avoid rate limits."""
    cur.execute("SELECT last_used FROM api_keys WHERE key_name = %s;", (key_name,))
    last_used = cur.fetchone()[0]
    
    if last_used:
        # Ensure last_used is timezone-aware for correct calculation
        if last_used.tzinfo is None:
            last_used = last_used.replace(tzinfo=datetime.timezone.utc)
            
        time_since_last_use = (datetime.datetime.now(datetime.timezone.utc) - last_used).total_seconds()
        if time_since_last_use < MIN_REQUEST_INTERVAL_SECONDS:
            sleep_time = MIN_REQUEST_INTERVAL_SECONDS - time_since_last_use
            logging.info(f"Throttling: key '{key_name}' used {time_since_last_use:.1f}s ago. Sleeping for {sleep_time:.1f}s.")
            time.sleep(sleep_time)

def update_key_and_log_usage(cur, key_name, task_id, token_count, request_type):
    """Updates key stats and logs the request."""
    cur.execute("""
        UPDATE api_keys
        SET last_used = NOW(),
            daily_request_count = daily_request_count + 1,
            daily_token_total = daily_token_total + %s
        WHERE key_name = %s;
    """, (token_count, key_name))

    cur.execute("""
        INSERT INTO usage_log (key_name, task_id, token_count, request_type)
        VALUES (%s, %s, %s, %s);
    """, (key_name, task_id, token_count, request_type))
    logging.info(f"Updated usage for key '{key_name}' in database.")

def update_task_context(cur, task_id, new_context):
    """Updates the context for a given task."""
    cur.execute("UPDATE tasks SET context = %s, last_updated = NOW() WHERE id = %s;",
                (json.dumps(new_context), task_id))
    logging.info(f"Updated context for task '{task_id}'.")

def send_slack_notification(message, level="info"):
    """Sends a notification to a Slack webhook."""
    webhook_url = "https://hooks.slack.com/services/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"
    
    color = {
        "info": "#36a64f",    # Green
        "warning": "#ffae42", # Orange
        "error": "#d50200"    # Red
    }.get(level, "#cccccc") # Default grey

    payload = {
        "attachments": [
            {
                "color": color,
                "title": f"Gemini Agent Notification ({level.upper()})",
                "text": message,
                "ts": datetime.datetime.now().timestamp()
            }
        ]
    }
    
    try:
        import requests
        response = requests.post(webhook_url, json=payload)
        if response.status_code != 200:
            logging.warning(f"Failed to send Slack notification. Status: {response.status_code}, Response: {response.text}")
    except Exception as e:
        logging.error(f"Exception while sending Slack notification: {e}", exc_info=True)
