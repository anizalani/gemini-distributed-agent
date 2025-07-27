# Gemini Distributed Agent

This project implements a distributed agent system for interacting with the Gemini CLI. It's designed to manage multiple API keys, rotate through them to avoid quota limits, and maintain a persistent context for conversations.

## Project Structure

```
/home/ubuntu/gemini-distributed-agent
├── .git/
├── venv/
├── .env.example            # Environment configuration template
├── .gitignore
├── gemini_agent.py
├── db_utils.py
├── populate_keys.py
├── reset_quota.sh
├── gemini-distributed-agent.md
├── requirements.txt
├── agent.log               # (Ignored by git)
└── README.md
```

## Setup

1.  **Environment Configuration:** This project uses a central `.env` file to manage all paths and credentials. Copy the example file and update it with your environment's paths:
    ```bash
    cp .env.example .env
    # Now, edit .env with your specific paths
    ```

2.  **Database:** The agent requires a PostgreSQL database. The path to the `.env` file containing your database credentials must be set in the `POSTGRES_ENV_FILE` variable in the main `.env` file.

3.  **API Keys:** The path to your Gemini API keys file must be set in the `API_KEYS_FILE` variable in the main `.env` file. The key file should have one key per line in the format `KEY_NAME=KEY_VALUE`.

4.  **Dependencies:** Install the required Python packages using the `requirements.txt` file:
    ```bash
    # Ensure you are in the project's virtual environment
    pip install -r requirements.txt
    ```

## Usage

To run the agent, execute the `gemini_agent.py` script and provide a prompt:

```bash
# Ensure you are in the project's virtual environment
python gemini_agent.py "Your prompt here"
```

## Cron Job

A daily cron job is set up to run `/home/ubuntu/gemini-distributed-agent/reset_quota.sh` to reset the API key usage statistics in the database. The cron job is configured to run the script within the project directory, ensuring it can access the `.env` file.
