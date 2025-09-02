import os
import json
import requests
import time
import uuid
import logging
import datetime
import subprocess
import shlex
from flask import Flask, request, jsonify, Response
from utils import db_utils

# --- Configuration ---
HOST = '0.0.0.0'
PORT = 8000
GEMINI_API_ENDPOINT = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:streamGenerateContent'
LOG_FILE = '/srv/gemini/proxy.log'

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[
                        logging.FileHandler(LOG_FILE),
                        logging.StreamHandler()
                    ])

app = Flask(__name__)

def get_gemini_api_key():
    """Fetches a single available Gemini API key from the database."""
    conn = None
    redis_conn = None
    try:
        conn = db_utils.get_db_connection()
        if not conn:
            raise Exception("Failed to connect to the database.")
        redis_conn = db_utils.get_redis_connection()
        with conn.cursor() as cur:
            key_info = db_utils.get_available_key(cur, redis_conn)
            if not key_info:
                raise Exception("No available Gemini API keys in the database.")
            return key_info[0], key_info[1] # key_name, key_value
    finally:
        if conn:
            conn.close()

def translate_chunk_to_openai_format(gemini_chunk):
    """Formats a Gemini stream chunk into the OpenAI ChatCompletionChunk format."""
    
    # Extract the text content from the Gemini chunk.
    # The structure is nested, so we need to safely navigate it.
    try:
        text_content = gemini_chunk['candidates'][0]['content']['parts'][0]['text']
    except (KeyError, IndexError):
        # If the expected structure isn't there, return an empty chunk
        # or handle the error as appropriate.
        return None

    return {
        "id": f"chatcmpl-{uuid.uuid4()}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": "gemini-pro-via-proxy",
        "choices": [{
            "index": 0,
            "delta": {
                "content": text_content,
            },
            "finish_reason": None 
        }]
    }

@app.route('/v1/chat/completions', methods=['POST'])
def chat_completions():
    """The main endpoint that mimics OpenAI's chat completion API with streaming."""
    logging.info("Received streaming request from AnythingLLM...")
    
    key_name = None
    try:
        key_name, api_key = get_gemini_api_key()
        logging.info(f"Successfully fetched Gemini API key '{key_name}' ending in ...{api_key[-4:]}")
    except Exception as e:
        logging.error(f"Failed to get API key: {e}")
        return jsonify({"error": str(e)}), 500

    openai_request = request.json
    user_prompt = ""
    if openai_request and 'messages' in openai_request:
        for message in reversed(openai_request['messages']):
            if message.get('role') == 'user':
                user_prompt = message.get('content')
                break
    
    if not user_prompt:
        logging.warning("Could not find a user prompt in the request.")
        return jsonify({"error": "Could not find a user prompt in the request."}), 400
    
    logging.info(f"Extracted prompt for streaming: '{user_prompt[:80]}...'")

    # Get the current date and format it
    current_date = datetime.datetime.now().strftime("%A, %B %d, %Y")
    system_prompt = f"Today is {current_date}. When asked for the date, use this information."

    headers = {'Content-Type': 'application/json'}
    params = {'key': api_key, 'alt': 'sse'}
    payload = {
        "contents": [
            {"role": "user", "parts": [{"text": user_prompt}]},
            {"role": "model", "parts": [{"text": system_prompt}]}
        ]
    }

    def generate():
        key_name_local = key_name
        try:
            logging.info(f"Forwarding streaming request to Gemini API at {GEMINI_API_ENDPOINT}")
            response = requests.post(GEMINI_API_ENDPOINT, headers=headers, params=params, json=payload, stream=True)
            response.raise_for_status()
            logging.info("Successfully connected to Gemini streaming endpoint.")

            for line in response.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    if line_str.startswith('data: '):
                        json_str = line_str[6:]
                        try:
                            gemini_chunk = json.loads(json_str)
                            openai_chunk = translate_chunk_to_openai_format(gemini_chunk)
                            if openai_chunk:
                                yield f"data: {json.dumps(openai_chunk)}\n\n"
                        except json.JSONDecodeError:
                            logging.warning(f"Could not decode JSON from line: {line_str}")
                            continue
            
            # Send the final [DONE] message to signify the end of the stream
            yield "data: [DONE]\n\n"
            logging.info("Stream finished. Sent [DONE] message.")

        except requests.exceptions.RequestException as e:
            logging.error(f"Error during streaming from Gemini API: {e}")
            # We can't return a normal error response as the stream has started.
            # We log it and the stream will just end.
        finally:
            if key_name_local:
                db_utils.release_key(key_name_local)
                logging.info(f"Released API key '{key_name_local}' back to the pool.")

    return Response(generate(), mimetype='text/event-stream')

import subprocess
import shlex

# --- Agent Execution Endpoint ---
# Define which commands are safe to run and which require a 'y/n' check
ALLOWED_COMMANDS = ['ls', 'read', 'write', 'find', 'cat']
CONFIRMATION_REQUIRED_COMMANDS = ['write']

@app.route('/execute-command', methods=['POST'])
def execute_command():
    data = request.get_json()
    if not data or 'command' not in data:
        return jsonify({'error': 'Invalid request: "command" is required'}), 400

    command = data.get('command')
    args = data.get('args', []) # args are optional

    if command not in ALLOWED_COMMANDS:
        return jsonify({'error': f'Command "{command}" is not allowed'}), 403

    # --- User Confirmation Step ---
    if command in CONFIRMATION_REQUIRED_COMMANDS:
        # Format the command for display in the terminal
        full_command_str = f"gemini-cli {command} 
{' '.join(args)}"
        
        # Prompt for confirmation in the terminal where this script is running
        logging.info(f"\n[AGENT ACTION] Attempting to execute: {full_command_str}")
        logging.info("Please confirm to proceed in the terminal (y/n): ")
        
        try:
            # Wait for user input from the console
            confirmation = input()
            if confirmation.lower() != 'y':
                logging.info("Execution cancelled by user.")
                return jsonify({
                    'stdout': '',
                    'stderr': 'Execution cancelled by user.',
                    'exit_code': -1
                }), 200
        except Exception as e:
             logging.error(f"Error during confirmation: {e}")
             return jsonify({'error': 'Failed to get user confirmation'}), 500

    # Sanitize arguments to prevent shell injection
    sanitized_args = [shlex.quote(str(arg)) for arg in args]
    
    try:
        # Construct the full command for subprocess
        final_command_array = ['gemini-cli', command] + sanitized_args
        
        logging.info(f"Executing command: {' '.join(final_command_array)}")

        result = subprocess.run(
            final_command_array,
            capture_output=True,
            text=True,
            timeout=60
        )

        logging.info(f"Command finished with exit code {result.returncode}")
        return jsonify({
            'stdout': result.stdout,
            'stderr': result.stderr,
            'exit_code': result.returncode
        })

    except FileNotFoundError:
        logging.error(f"Command 'gemini-cli' not found. Make sure it is in the system's PATH.")
        return jsonify({'error': "Command 'gemini-cli' not found."}), 500
    except Exception as e:
        logging.error(f"An error occurred while executing the command: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    logging.info(f"Starting Gemini-OpenAI Proxy Server at http://{HOST}:{PORT}")
    app.run(host=HOST, port=PORT)

