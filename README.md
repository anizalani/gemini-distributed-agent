# Gemini Distributed Agent

The Gemini Distributed Agent is a powerful, database-backed system for interacting with the Gemini CLI. It is designed for robust, continuous operation by intelligently managing multiple API keys, maintaining conversational context, and providing a flexible interface for both interactive and automated tasks.

## Features

-   **Automated API Key Rotation:** Cycles through a pool of API keys stored in a database to avoid rate limits and daily quotas.
-   **Persistent Context:** Saves conversation history in a PostgreSQL database, allowing the agent to resume tasks with full context, even across different machines.
-   **Usage Tracking:** Logs all API requests and token usage for auditing and performance monitoring.
-   **Flexible Execution Modes:** Supports interactive, agentic (autonomous), and single-request modes.
-   **Customizable Permissions:** Features a configurable permission system to control which shell commands the agent can execute.
-   **Slack Notifications:** Can send real-time notifications for important events like key exhaustion or errors.
-   **Simplified Alias:** Comes with a pre-configured `gemma` command for easy, system-wide access.

## Setup

1.  **Environment Configuration:** The project is configured through a central `.env` file. Copy the example file and update it with your environment's specific paths:
    ```bash
    cp .env.example .env
    # Edit .env with your database and API key file paths
    ```

2.  **Database:** The agent requires a PostgreSQL database. Ensure the path to your database credentials file is set in the `POSTGRES_ENV_FILE` variable in the main `.env` file.

3.  **API Keys:** The path to your Gemini API keys file must be set in the `API_KEYS_FILE` variable. The key file should contain one key per line in the format `KEY_NAME=KEY_VALUE`.

4.  **Populate Keys:** Once your `.env` file is configured, populate the database with your API keys by running:
    ```bash
    python3 populate_keys.py
    ```

5.  **Dependencies:** Install the required Python packages:
    ```bash
    pip install -r requirements.txt
    ```

## Usage

The primary way to interact with the agent is through the `gemma` command, which is a system-wide alias for the `gemma-exec` script.

### The `gemma` Command

The `gemma` command simplifies interaction by automatically providing the agent with its necessary operational context. You provide the task instructions via a file.

```bash
gemma --file /path/to/your/instructions.md
```

The agent will process the instructions from the file, using its long-term memory to maintain context from previous interactions.

### Direct Script Execution & Command-Line Flags

For more advanced use cases, you can run the agent script directly. This allows you to use command-line flags to control its behavior.

**Syntax:**
```bash
python3 gemini_agent.py "<prompt>" [flags]
```

**Example:**
```bash
python3 gemini_agent.py "Summarize the attached document." --file /path/to/document.txt --interactive
```

#### **Command-Line Flags:**

| Flag              | Description                                                                                                     |
| ----------------- | --------------------------------------------------------------------------------------------------------------- |
| `prompt`          | (Required) The initial prompt or instruction for the agent.                                                     |
| `--interactive`   | If set, the agent will ask for user confirmation before executing any shell commands.                             |
| `--agentic`       | If set, the agent will execute shell commands autonomously until the task is complete.                            |
| `--permissions`   | Sets the permission level for command execution. Choices: `weak` (default) or `superuser`.                        |
| `--task-id`       | Specifies a task ID to resume. If not provided, a new one is generated based on the hostname and date.            |

**Note:** You cannot use `--interactive` and `--agentic` at the same time.

## How It Works

### API Key Rotation

The agent queries the PostgreSQL database to find an available API key that has not exceeded its daily request or token limits. It intelligently throttles requests to avoid hitting the per-minute rate limits, and will automatically sleep and retry if all keys are temporarily exhausted.

### Task Context Management

Each interaction is tied to a `task_id`. The agent stores the entire conversation history (prompts and responses) as a JSON object in the database. When a new prompt is given with an existing `task_id`, the agent retrieves the history, providing the full context for the new request. This allows for complex, multi-step tasks to be completed over time.

## Project Structure

```
/
├── .env                  # Main configuration file
├── .env.example          # Example configuration
├── agent_config.json     # Permissions configuration
├── agent.log             # Agent activity log
├── db_utils.py           # Database interaction logic
├── gemini_agent.py       # Core agent script
├── populate_keys.py      # Script to populate API keys
├── requirements.txt      # Python dependencies
├── gemma-exec            # Wrapper script for easy use (aliased to gemma)
└── venv/                 # Python virtual environment
```