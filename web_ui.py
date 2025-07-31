
import os
import psycopg2
import json
import pytz
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, render_template_string, send_from_directory

# --- Configuration ---
# Load database credentials from the .postgres.env file
dotenv_path = os.path.join(os.path.dirname(__file__), '.postgres.env')
load_dotenv(dotenv_path=dotenv_path)

DB_NAME = os.getenv("POSTGRES_DB")
DB_USER = os.getenv("POSTGRES_USER")
DB_PASS = os.getenv("POSTGRES_PASSWORD")
DB_HOST = os.getenv("POSTGRES_HOST")
DB_PORT = os.getenv("POSTGRES_PORT")
TARGET_TZ = pytz.timezone('America/Chicago')

# --- Flask App Initialization ---
app = Flask(__name__)
LOGS_DIR = os.path.join(app.root_path, 'gemma_logs')

# --- HTML Template ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Gemini Agent - {{ title }}</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; background-color: #f4f4f9; color: #333; margin: 0; padding: 0; }
        h1 { color: #444; text-align: center; margin-top: 2rem; }
        table { width: 100%; border-collapse: collapse; margin-top: 1rem; box-shadow: 0 2px 15px rgba(0,0,0,0.1); background-color: #fff; }
        th, td { padding: 12px 15px; text-align: left; border-bottom: 1px solid #ddd; white-space: pre-wrap; word-wrap: break-word; }
        thead { background-color: #007bff; color: #ffffff; }
        tr:nth-child(even) { background-color: #f2f2f2; }
        tr:hover { background-color: #e9ecef; }
        .container { max-width: 95%; margin: auto; padding: 2rem; }
        .no-data { text-align: center; padding: 2rem; font-size: 1.2rem; color: #777; }
        nav { background-color: #333; padding: 1rem; text-align: center; }
        nav a { color: white; text-decoration: none; padding: 1rem; font-weight: bold; }
        nav a:hover { background-color: #555; }
    </style>
</head>
<body>
    <nav>
        <a href="/">Usage Logs</a>
        <a href="/tasks">Tasks</a>
        <a href="/keys">API Keys</a>
        <a href="/interactions">Interactions</a>
        <a href="/command_log">Command Log</a>
        <a href="/gemma_logs">Gemma Logs</a>
    </nav>
    <div class="container">
        <h1>{{ title }}</h1>
        {% if error %}
            <p class="no-data">Error: {{ error }}</p>
        {% elif data %}
            <table>
                <thead>
                    <tr>
                        {% for header in headers %}
                            <th>{{ header }}</th>
                        {% endfor %}
                    </tr>
                </thead>
                <tbody>
                    {% for row in data %}
                        <tr>
                            {% for item in row %}
                                <td>{{ item }}</td>
                            {% endfor %}
                        </tr>
                    {% endfor %}
                </tbody>
            </table>
        {% else %}
            <p class="no-data">No entries found.</p>
        {% endif %}
    </div>
</body>
</html>
"""

def get_db_connection():
    """Establishes a connection to the PostgreSQL database."""
    try:
        conn = psycopg2.connect(
            dbname=DB_NAME, user=DB_USER, password=DB_PASS, host=DB_HOST, port=DB_PORT
        )
        return conn
    except psycopg2.OperationalError as e:
        print(f"Database connection failed: {e}")
        return None

def convert_to_local_time(utc_dt):
    """Converts a UTC datetime object to the target timezone."""
    if utc_dt and isinstance(utc_dt, datetime):
        return utc_dt.replace(tzinfo=pytz.utc).astimezone(TARGET_TZ).strftime('%Y-%m-%d %H:%M:%S %Z')
    return utc_dt

@app.route('/')
def index():
    """Fetches usage logs and displays them."""
    data = []
    headers = []
    error_message = None
    conn = get_db_connection()
    if not conn:
        error_message = "Failed to connect to the database."
    else:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT id, key_name, task_id, request_timestamp, token_count, request_type FROM usage_log ORDER BY request_timestamp DESC;")
                headers = [desc[0] for desc in cur.description]
                rows = cur.fetchall()
                for row in rows:
                    row = list(row)
                    row[3] = convert_to_local_time(row[3]) # Convert timestamp
                    data.append(row)
        except psycopg2.Error as e:
            error_message = f"Database query failed: {e}"
        finally:
            conn.close()
    return render_template_string(HTML_TEMPLATE, data=data, headers=headers, error=error_message, title="Database Usage Logs")

@app.route('/tasks')
def view_tasks():
    """Fetches tasks and displays them."""
    data = []
    headers = []
    error_message = None
    conn = get_db_connection()
    if not conn:
        error_message = "Failed to connect to the database."
    else:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT id, status, last_updated, context FROM tasks ORDER BY last_updated DESC;")
                headers = [desc[0] for desc in cur.description]
                rows = cur.fetchall()
                for row in rows:
                    row = list(row)
                    row[2] = convert_to_local_time(row[2]) # Convert timestamp
                    row[3] = json.dumps(row[3], indent=2) # Pretty-print JSON
                    data.append(row)
        except psycopg2.Error as e:
            error_message = f"Database query failed: {e}"
        finally:
            conn.close()
    return render_template_string(HTML_TEMPLATE, data=data, headers=headers, error=error_message, title="Tasks")

@app.route('/keys')
def view_keys():
    """Fetches API key status and displays it."""
    data = []
    headers = []
    error_message = None
    conn = get_db_connection()
    if not conn:
        error_message = "Failed to connect to the database."
    else:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT key_name, daily_request_count, daily_token_total, last_used, quota_exhausted, disabled_until FROM api_keys ORDER BY last_used DESC;")
                headers = [desc[0] for desc in cur.description]
                rows = cur.fetchall()
                for row in rows:
                    row = list(row)
                    row[3] = convert_to_local_time(row[3]) # Convert last_used
                    row[5] = convert_to_local_time(row[5]) # Convert disabled_until
                    data.append(row)
        except psycopg2.Error as e:
            error_message = f"Database query failed: {e}"
        finally:
            conn.close()
    return render_template_string(HTML_TEMPLATE, data=data, headers=headers, error=error_message, title="API Key Status")

@app.route('/interactions')
def view_interactions():
    """Fetches all interactions from the database, newest first."""
    data = []
    headers = []
    error_message = None
    conn = get_db_connection()
    if not conn:
        error_message = "Failed to connect to the database."
    else:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT id, task_id, prompt, response, request_timestamp FROM interactions ORDER BY request_timestamp DESC;")
                headers = [desc[0] for desc in cur.description]
                rows = cur.fetchall()
                for row in rows:
                    row = list(row)
                    row[4] = convert_to_local_time(row[4]) # Convert timestamp
                    data.append(row)
        except psycopg2.Error as e:
            error_message = f"Database query failed: {e}"
        finally:
            conn.close()
    return render_template_string(HTML_TEMPLATE, data=data, headers=headers, error=error_message, title="All Interactions")

@app.route('/command_log')
def view_command_log():
    """Fetches the command log and displays it."""
    data = []
    headers = []
    error_message = None
    conn = get_db_connection()
    if not conn:
        error_message = "Failed to connect to the database."
    else:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT id, task_id, executed_at, command, permissions, user_confirmation, agent_mode FROM command_log ORDER BY executed_at DESC;")
                headers = [desc[0] for desc in cur.description]
                rows = cur.fetchall()
                for row in rows:
                    row = list(row)
                    row[2] = convert_to_local_time(row[2]) # Convert timestamp
                    data.append(row)
        except psycopg2.Error as e:
            error_message = f"Database query failed: {e}"
        finally:
            conn.close()
    return render_template_string(HTML_TEMPLATE, data=data, headers=headers, error=error_message, title="Command Log")

@app.route('/gemma_logs', defaults={'filename': None})
@app.route('/gemma_logs/<path:filename>')
def view_gemma_logs(filename):
    """Serves a specific log file or lists all available logs."""
    if filename:
        return send_from_directory(LOGS_DIR, filename)
    else:
        # List all log files
        try:
            files = [f for f in os.listdir(LOGS_DIR) if os.path.isfile(os.path.join(LOGS_DIR, f))]
            files.sort(reverse=True)
            
            # Simple HTML for listing files
            file_list_html = "<ul>"
            for f in files:
                file_list_html += f'<li><a href="/gemma_logs/{f}">{f}</a></li>'
            file_list_html += "</ul>"

            # Using a simplified template for the file list
            list_template = """
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <title>Gemini Agent - Gemma Logs</title>
                <style>
                    body { font-family: sans-serif; margin: 2em; }
                    ul { list-style-type: none; padding: 0; }
                    li { margin: 0.5em 0; }
                    a { text-decoration: none; color: #007bff; }
                    a:hover { text-decoration: underline; }
                </style>
            </head>
            <body>
                <h1>Available Gemma Logs</h1>
                {{ file_list_html|safe }}
            </body>
            </html>
            """
            return render_template_string(list_template, file_list_html=file_list_html)

        except FileNotFoundError:
            return "Log directory not found.", 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002, debug=True)

