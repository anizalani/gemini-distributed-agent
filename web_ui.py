from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

import os
import subprocess
from flask import Flask, render_template, Response, request
import logging
from queue import Queue
from threading import Thread
import psycopg2
import pytz
from datetime import datetime

# Database connection details from .postgres.env
DB_NAME = os.getenv('POSTGRES_DB')
DB_USER = os.getenv('POSTGRES_USER')
DB_PASSWORD = os.getenv('POSTGRES_PASSWORD')
DB_HOST = os.getenv('POSTGRES_HOST')
DB_PORT = os.getenv('POSTGRES_PORT')

# Add debug prints here
print(f"DEBUG (web_ui.py - env): POSTGRES_DB={os.getenv('POSTGRES_DB')}")
print(f"DEBUG (web_ui.py - env): POSTGRES_USER={os.getenv('POSTGRES_USER')}")
print(f"DEBUG (web_ui.py - env): POSTGRES_HOST={os.getenv('POSTGRES_HOST')}")
print(f"DEBUG (web_ui.py - env): POSTGRES_PORT={os.getenv('POSTGRES_PORT')}")
print(f"DEBUG (web_ui.py - env): PGPASSWORD={'*' * len(os.getenv('POSTGRES_PASSWORD')) if os.getenv('POSTGRES_PASSWORD') else 'None'}")

def get_db_connection():
    print(f"DEBUG (web_ui.py): Attempting to connect to DB: host={DB_HOST}, port={DB_PORT}, dbname={DB_NAME}, user={DB_USER}")
    conn = psycopg2.connect(database=DB_NAME, user=DB_USER, password=DB_PASSWORD, host=DB_HOST, port=DB_PORT)
    return conn

# Configure logging
log_dir = os.getenv('GEMINI_WORKSPACE', '/tmp')
log_file = os.path.join(log_dir, 'web_ui.log')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename=log_file,
    filemode='a'
)
logger = logging.getLogger(__name__)

import json

app = Flask(__name__)

def from_json_filter(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            pass
    return value

app.jinja_env.filters['from_json'] = from_json_filter

# --- Paths ---
CODE_DIR = "/srv/gemini"
LAUNCHER = os.path.join(CODE_DIR, "launcher/launch_gemini_task.sh")

# --- Process Management ---
# WARNING: This is a simple solution for a single-user, single-process server.
# It will not scale to multiple users. A more robust solution would use
# a proper session management and process manager.
process = None
process_queue = Queue()

def process_manager(proc):
    """Read from the process's stdout and push to a queue."""
    for line in iter(proc.stdout.readline, ''):
        process_queue.put(line)
    proc.stdout.close()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/run')
def run():
    global process
    mode = request.args.get('mode')
    if not mode:
        return Response("Missing 'mode' parameter", status=400)

    def generate():
        global process
        try:
            # Terminate any existing process
            if process and process.poll() is None:
                process.terminate()
                process.wait()

            # Generate a unique TASK_ID
            env = os.environ.copy()
            env['TZ'] = 'America/Chicago'
            task_id_process = subprocess.run(
                ["date", "+%F-%H%M"],
                capture_output=True, text=True, check=True, env=env
            )
            task_id = task_id_process.stdout.strip()

            command = [LAUNCHER, task_id, mode]
            logger.info(f"Executing command: {' '.join(command)}")

            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )

            # Start a thread to read from the process's stdout
            thread = Thread(target=process_manager, args=(process,))
            thread.daemon = True
            thread.start()

            while process.poll() is None or not process_queue.empty():
                try:
                    line = process_queue.get(timeout=0.1)
                    yield f"data: {line.strip()}\n\n"
                except Exception:
                    # Timeout just means no new output
                    pass

            logger.info(f"Command finished with exit code {process.returncode}")

        except subprocess.CalledProcessError as e:
            logger.error(f"Error executing command: {e}")
            yield f"data: Error: {e}\n\n"
        except Exception as e:
            logger.error(f"An unexpected error occurred: {e}")
            yield f"data: An unexpected error occurred: {e}\n\n"

    return Response(generate(), mimetype='text/event-stream')

@app.route('/db_status')
def db_status():
    tables = []
    active_connections = []
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Get list of tables
        cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name;")
        tables = [row[0] for row in cur.fetchall()]

        # Get active connections
        cur.execute("SELECT pid, usename, datname, client_addr, client_port, backend_start, state, query FROM pg_stat_activity WHERE datname = %s ORDER BY backend_start DESC;", (DB_NAME,))
        raw_connections = cur.fetchall()

        chicago_tz = pytz.timezone('America/Chicago')
        for conn_data in raw_connections:
            # Convert backend_start to America/Chicago timezone
            if conn_data[5] and isinstance(conn_data[5], datetime):
                # If the datetime object is naive, assume UTC (common for DBs)
                if conn_data[5].tzinfo is None:
                    utc_dt = pytz.utc.localize(conn_data[5])
                else:
                    utc_dt = conn_data[5].astimezone(pytz.utc)
                local_dt = utc_dt.astimezone(chicago_tz)
                active_connections.append(conn_data[:5] + (local_dt.strftime('%Y-%m-%d %H:%M:%S %Z'),) + conn_data[6:])
            else:
                active_connections.append(conn_data)

    except Exception as e:
        logger.error(f"Error fetching database status: {e}")
        return render_template('db_status.html', error=str(e))
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

    return render_template('db_status.html', tables=tables, active_connections=active_connections)

@app.route('/view_table/<table_name>')
def view_table(table_name):
    data = []
    columns = []
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # Sanitize table_name to prevent SQL injection
        cur.execute("SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = %s", (table_name,))
        if cur.fetchone() is None:
            raise ValueError("Table not found")

        cur.execute(f'SELECT id, content, created_at, gemini_model, gemini_output, source_documents, token_count FROM "{table_name}" ORDER BY id DESC;')
        raw_data = cur.fetchall()
        columns = [desc[0] for desc in cur.description]

        # Find the 'created_at' column index if it exists
        created_at_index = -1
        if 'created_at' in columns:
            created_at_index = columns.index('created_at')

        chicago_tz = pytz.timezone('America/Chicago')

        for row in raw_data:
            row_list = list(row)
            if created_at_index != -1 and row_list[created_at_index] and isinstance(row_list[created_at_index], datetime):
                utc_dt = row_list[created_at_index].astimezone(pytz.utc)
                row_list[created_at_index] = utc_dt.astimezone(chicago_tz)
            data.append(row_list)

    except Exception as e:
        logger.error(f"Error viewing table {table_name}: {e}")
        return render_template('view_table.html', error=str(e), table_name=table_name)
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
    return render_template('view_table.html', table_name=table_name, columns=columns, data=data)

@app.route('/send', methods=['POST'])
def send():
    global process
    if not process or process.poll() is not None:
        return Response("No active process", status=400)

    message = request.json.get('message')
    if not message:
        return Response("Missing 'message' parameter", status=400)

    try:
        process.stdin.write(message + '\n')
        process.stdin.flush()
        return Response("Message sent", status=200)
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        return Response(f"Error: {e}", status=500)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)