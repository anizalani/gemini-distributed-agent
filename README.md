# Gemini Distributed Agent - Consolidated Documentation

**Last updated:** Tue Sep  2 19:59:38 CDT 2025

---

## 1. System Overview

The Gemini Distributed Agent is a powerful, database-backed system for running Google's Gemini model in a persistent, multi-agent environment. It is designed to overcome the limitations of the free tier by intelligently managing a pool of API keys, and it provides a robust framework for logging, monitoring, and context management.

The system has three main components:

*   **Launcher (`launch_gemini_task.sh`):** The primary entry point for the system. This script wraps the standard `@google/gemini-cli`, integrating it with the project's database backend for persistent logging, context management, and API key rotation.
*   **PostgreSQL Database:** The heart of the system. It stores everything from API key usage and task history to command logs and user profiles. This allows for a complete audit trail of all agent activity and enables long-term memory and inter-agent coordination.
*   **Web UI (`web_ui.py`):** A Flask-based web application that provides a real-time view into the agent's operations by displaying the contents of the various database tables.

---

## 2. Features

*   **Agentic & Interactive Modes**: Run the agent in fully autonomous mode (`--agentic`) or have it request confirmation before executing commands (`--interactive`).
*   **Relational Database Backend**: All actions are logged to a PostgreSQL database, providing a complete audit trail.
*   **Intelligent API Key Management**: The system intelligently rotates through a pool of API keys, selecting the best one based on its current usage, quota status, and last use time.
*   **Web UI for Monitoring**: A built-in Flask web application provides a real-time view into the agent's operations.
*   **Extensible Schema**: The database schema is designed to be extensible, with support for advanced features like user profiles, home network mapping, and custom knowledge bases.

---

## 3. Setup and Installation

1.  **Clone the Repository**
    ```bash
    git clone <repository-url>
    cd gemini-distributed-agent
    ```

2.  **Create a Virtual Environment**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Install Dependencies**
    ```bash
    pip install -r requirements.txt
    npm install
    ```

4.  **Configure Environment Variables**
    *   Copy `.postgres.env.example` to `.postgres.env` and fill in your database credentials.
    *   Copy `.env.example` to `.env` and set the `CODE_DIR` and `GEMINI_WORKSPACE` variables.

5.  **Setup Symlinks (Optional)**

    Run the `setup_symlinks.sh` script to create a system-wide `gembot` command.

    ```bash
    bash setup_symlinks.sh
    ```

---

## 4. Usage

### 4.1. Using the `gembot` Command

A convenient way to run the Gemini Distributed Agent is to use the `gembot` command, which is a symlink to the `gembot.sh` script. This script provides a menu-driven interface for launching the agent in different modes.

```bash
gembot
```

This will present you with a menu of options:

*   **Interactive Mode:** The default mode, for direct interaction with the agent.
*   **Headless Mode:** For single-shot commands.
*   **Context-Aware Mode:** Interactive session with all files in the current directory as context.
*   **Agentic Mode:** Autonomous execution of a prompt.

### 4.2. Running a Task Directly

The primary entry point for the Gemini Distributed Agent is the `launch_gemini_task.sh` script.

```bash
./launcher/launch_gemini_task.sh <task_id> [mode]
```

**Arguments:**

| Argument  | Description                                                                                             |
|-----------|---------------------------------------------------------------------------------------------------------|
| `task_id` | A unique identifier for the aask (e.g., `refactor-api-20250728`). This is used to group all related logs. |
| `mode`    | (Optional) The operational mode. Defaults to `interactive`.                                             |

**Example:**

```bash
# Start a new interactive session for a refactoring task
./launcher/launch_gemini_task.sh refactor-web-ui-websockets
```

### 4.2. Running the Web UI

The web UI provides a real-time view of the agent's database.

1.  **Activate the virtual environment:**
    ```bash
    source venv/bin/activate
    ```

2.  **Run the web server:**
    ```bash
    python3 web_ui.py
    ```

3.  **Access in your browser:**
    Open your web browser and navigate to `http://<your-server-ip>:8080`.

---

## 5. Database Schema

The PostgreSQL database is central to the operation of the Gemini Distributed Agent. Here is a comprehensive overview of the schema:

### `api_keys`
Tracks usage limits and throttling per API key.

| Column                | Type      | Description                               |
|-----------------------|-----------|-------------------------------------------|
| `id`                  | SERIAL    | Primary key.                              |
| `key_name`            | TEXT      | A unique name for the key.                |
| `key_value`           | TEXT      | The API key itself.                       |
| `last_used`           | TIMESTAMP | When the key was last used.               |
| `quota_exhausted`     | BOOLEAN   | Whether the key's quota is exhausted.     |
| `daily_request_count` | INT       | The number of requests made with the key today. |
| `daily_token_total`   | INT       | The total number of tokens used by the key today. |
| `disabled_until`      | TIMESTAMP | A timestamp until which the key is disabled. |
| `priority`            | INT       | The priority of the key for selection.    |
| `assigned_user`       | TEXT      | The user the key is assigned to.          |
| `rotating`            | BOOLEAN   | Whether the key is part of the rotation.  |
| `source`              | TEXT      | The source of the key.                    |

### `tasks`
Stores high-level information about each task.

| Column         | Type      | Description                               |
|----------------|-----------|-------------------------------------------|
| `id`           | TEXT      | Primary key. A unique identifier for the task. |
| `context`      | JSONB     | The context of the task.                  |
| `last_updated` | TIMESTAMP | When the task was last updated.           |
| `status`       | TEXT      | The status of the task.                   |

### `interactions`
A complete history of every prompt and response.

| Column      | Type      | Description                               |
|-------------|-----------|-------------------------------------------|
| `id`        | SERIAL    | Primary key.                              |
| `task_id`   | TEXT      | The ID of the task this interaction belongs to. |
| `prompt`    | TEXT      | The prompt given to the agent.            |
| `response`  | TEXT      | The response from the agent.              |
| `timestamp` | TIMESTAMP | When the interaction occurred.            |

### `command_log`
A log of every command the agent attempts to execute.

| Column              | Type      | Description                               |
|---------------------|-----------|-------------------------------------------|
| `id`                | SERIAL    | Primary key.                              |
| `task_id`           | TEXT      | The ID of the task this command belongs to. |
| `executed_at`       | TIMESTAMP | When the command was executed.            |
| `prompt`            | TEXT      | The prompt that led to the command.       |
| `response`          | TEXT      | The response from the agent.              |
| `command`           | TEXT      | The command that was executed.            |
| `permissions`       | TEXT      | The permissions used to execute the command. |
| `user_confirmation` | BOOLEAN   | Whether the user confirmed the command.   |
| `agent_mode`        | TEXT      | The mode the agent was in at the time.    |

### Other Tables
The documentation also mentions a number of other tables that can be used to extend the functionality of the system, including:

*   `usage_log`
*   `command_output`
*   `project_files`
*   `knowledge`
*   `user_profile`
*   `home_network`
*   `permissions_profile`
*   `custom_knowledge`
*   `token_prediction_log`
*   `vector_knowledge`
*   `subtasks`
*   `agents`
*   `task_queue`

---

## 6. Key Management and Quotas

The system uses a sophisticated, database-backed approach to manage a pool of API keys and handle API quotas.

### 6.1. Key Selection

When a new task is started, the `select_key.py` script is called to select a usable API key from the `api_keys` table. The script uses the following criteria to select a key:

1.  The key is not marked as `quota_exhausted`.
2.  The key is not `disabled_until` a future time.
3.  The key with the lowest `daily_request_count` is selected first, then the lowest `daily_token_total`, and finally the oldest `last_used` timestamp.

This load balancing strategy helps to maximize the usage of the available keys and avoid hitting quota limits.

### 6.2. Quota Management

The system has a basic but effective way of managing API quotas:

*   **Usage Tracking:** When a key is used, the `daily_request_count` is incremented, and the `last_used` timestamp is updated.
*   **Manual Quota Flag:** You can manually set the `quota_exhausted` flag to `TRUE` in the database to prevent a key from being selected.
*   **Temporary Disabling:** You can use the `disabled_until` timestamp to temporarily disable a key.

### 6.3. Daily Quota Reset

The documentation suggests setting up a daily cron job to reset the quota-related fields in the `api_keys` table:

```bash
0 8 * * * psql your_db -c "
  UPDATE api_keys SET
    daily_token_total = 0,
    daily_request_count = 0,
    quota_exhausted = FALSE,
    disabled_until = NULL;"
```

---

## 7. Configuration

The application is configured through a combination of environment variables and JSON files.

### 7.1. `.postgres.env`

This file contains the connection details for the PostgreSQL database:

```
POSTGRES_DB=postgres
POSTGRES_USER=gemini_user
POSTGRES_PASSWORD="your_password_here"
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
```

### 7.2. `.env`

This file is used to configure other environment variables for the application.

*   `CODE_DIR`: The absolute path to the project directory.
*   `GEMINI_WORKSPACE`: The absolute path to the directory where logs and other artifacts will be stored.

```
CODE_DIR=/path/to/your/project
GEMINI_WORKSPACE=/path/to/your/workspace
```

### 7.2. `llm_platform_config.json`

This file is used by the `llm_router.py` script and contains API keys for various LLM platforms. **Note that the web UI does not use this file.**

```json
{
    "gemini": {
        "key1": "YOUR_API_KEY_HERE",
        "key2": "YOUR_API_KEY_HERE",
        ...
    },
    "openai": {
        "api_key": "YOUR_OPENAI_API_KEY"
    },
    "merlin": {
        "api_key": "YOUR_MERLIN_API_KEY"
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "model": "llama3"
    }
}
```

### 7.3. `agent_config.json`

This file is used to configure the permissions for the agent.

```json
{
    "permissions": {
        "superuser": {
            "denylist": [
                "shutdown"
            ]
        },
        "weak": {
            "allowlist": [
                "ls",
                "docker",
                ...
            ]
        }
    }
}
```
## 8. Project Components and Their Roles

This section provides a detailed overview of the key scripts and modules within the project, explaining their purpose and how they contribute to the overall system.

### Shell Scripts (`.sh`)

*   **`gembot.sh`**:
    *   **Purpose:** The primary entry point for users. This script orchestrates the entire agent environment, including setting up the Python virtual environment, installing dependencies, starting the web UI (if not running), and presenting a menu-driven interface to launch the Gemini agent in various operational modes.
    *   **Role:** Core orchestration and user interface.

*   **`launcher/launch_gemini_task.sh`**:
    *   **Purpose:** Called by `gembot.sh`, this script is responsible for the core execution flow of a Gemini task. It selects an appropriate API key, ensures the `@google/gemini-cli` is installed and up-to-date, and executes the CLI with specific arguments based on the chosen mode (interactive, headless, context, agentic). It also triggers post-session API usage tracking.
    *   **Role:** Task execution and environment setup for the Gemini CLI.

*   **`deploy.sh`**:
    *   **Purpose:** Automates the initial deployment of the Gemini Distributed Agent on a new host. It handles repository cloning, virtual environment creation, and dependency installation (Python and Node.js).
    *   **Role:** One-time setup and deployment utility.

*   **`setup_symlinks.sh`**:
    *   **Purpose:** Creates a symbolic link from `/usr/local/bin/gembot` to the `gembot.sh` script, making the `gembot` command accessible system-wide for user convenience.
    *   **Role:** System integration utility.

*   **`reset_quota.sh`**:
    *   **Purpose:** Resets the daily API request and token counts for all API keys in the PostgreSQL database. This script is designed to be run periodically, typically via a cron job, to ensure daily quotas are refreshed.
    *   **Role:** Maintenance utility for API quota management.

### Python Scripts (`.py`)

*   **`web_ui.py`**:
    *   **Purpose:** A Flask-based web application that provides a real-time monitoring interface for the agent's operations. It displays usage logs, tasks, API key status, interaction history, and command logs from the PostgreSQL database.
    *   **Role:** User interface and monitoring.

*   **`gemini_openai_proxy.py`**:
    *   **Purpose:** Acts as a proxy server that mimics OpenAI's Chat Completion API, allowing other applications (like AnythingLLM) to interact with Gemini through a familiar interface. It also contains logic for executing shell commands generated by the agent, including permission checks and user confirmation.
    *   **Role:** API translation, LLM integration, and agent action execution.

*   **`utils/db_utils.py`**:
    *   **Purpose:** A collection of utility functions for interacting with the PostgreSQL database and Redis. This includes establishing connections, retrieving and releasing API keys, logging interactions, commands, and usage data, and sending Slack notifications.
    *   **Role:** Centralized database and Redis interaction layer.

*   **`integrations/anything_llm.py`**:
    *   **Purpose:** Provides specific integration logic for sending prompts and context to the AnythingLLM API.
    *   **Role:** External LLM integration.

*   **`check_env.py`**:
    *   **Purpose:** A simple utility script to print the values of key environment variables, useful for debugging environment setup issues.
    *   **Role:** Debugging utility.

*   **`export_keys.py`**:
    *   **Purpose:** Fetches API keys from the PostgreSQL database and exports them to `llm_platform_config.json`. This is useful for populating the `llm_platform_config.json` file if `llm_router.py` is used.
    *   **Role:** Key management utility.

*   **`gemini_agent.py`**:
    *   **Purpose:** Contains the core logic for the Gemini agent's decision-making process. It handles prompt processing, interaction with the Gemini API (via `run_gemini_command`), parsing generated commands, and managing the agent's conversational flow.
    *   **Role:** Core agent intelligence and control.

*   **`integrations/slack_bot.py`**:
    *   **Purpose:** Implements a Slack bot that listens for mentions and executes commands (e.g., `gemma` commands) in a background thread, sending results back to Slack.
    *   **Role:** Slack integration for direct command execution.

*   **`integrations/slack_command_handler.py`**:
    *   **Purpose:** Handles incoming Slack slash commands, verifies requests, and dispatches background tasks to run Gemini scripts and respond to Slack.
    *   **Role:** Slack integration for slash command processing.

*   **`launcher/scripts/log_session.py`**:
    *   **Purpose:** Logs detailed session information to the database after a Gemini CLI session has concluded.
    *   **Role:** Post-session logging utility.

*   **`launcher/scripts/populate_context.py`**:
    *   **Purpose:** Scans a specified directory for relevant files and populates their content into the database as context for a given task. This allows the agent to have a persistent memory of project files.
    *   **Role:** Context management utility.

*   **`launcher/scripts/select_key.py`**:
    *   **Purpose:** Selects the most suitable API key from the PostgreSQL database based on availability, usage statistics, and quota status. It uses a transaction-safe mechanism to prevent race conditions.
    *   **Role:** Core API key selection logic.

*   **`launcher/scripts/setup_database.py`**:
    *   **Purpose:** A one-time script to set up the PostgreSQL database, create the necessary tables, and apply the initial schema.
    *   **Role:** Database setup utility.

*   **`launcher/scripts/track_api_usage.py`**:
    *   **Purpose:** Tracks the usage of individual API keys by incrementing request counts and marking keys as quota-exhausted when limits are reached.
    *   **Role:** API usage tracking and quota enforcement.

*   **`llm_router.py`**:
    *   **Purpose:** Routes incoming LLM prompts to different backend LLM platforms (Gemini, OpenAI, Ollama) based on keywords in the prompt. It uses `llm_platform_config.json` for API key configuration.
    *   **Role:** LLM backend routing.

*   **`utils/view_logs.py`**:
    *   **Purpose:** Connects to the database and prints recent log entries, providing a command-line way to inspect agent activity.
    *   **Role:** Log viewing utility.

### Archived Files (No Longer in Active Use)

The following files have been moved to the `gemini-distributed-agent-archive` directory because their functionality has been superseded, they are redundant, or they represent older approaches.

*   **`launcher/scripts/reset_api_quotas.sh`**: Redundant; superseded by `reset_quota.sh`.
*   **`scripts/deploy.sh`**: Redundant; superseded by the main `deploy.sh` in the project root.
*   **`scripts/old-gemini-key.sh`**: Obsolete; key management is now handled by the database system.
*   **`scripts/run-gemini.sh`**: Superseded by `gembot.sh` and `launcher/launch_gemini_task.sh` for running Gemini tasks.
*   **`scripts/webui.sh`**: Superseded by `gembot.sh` for web UI management.
*   **`gemini_interactive_wrapper.py`**: Superseded by the integrated workflow managed by `gembot.sh` and `launcher/launch_gemini_task.sh`.
*   **`launcher/gemini_agent.py`**: Duplicate of `gemini_agent.py`.
*   **`scripts/select_key.py`**: Redundant wrapper; the core logic is in `launcher/scripts/select_key.py`.
*   **`utils/populate_context.py`**: Duplicate of `launcher/scripts/populate_context.py`.
*   **`utils/populate_keys.py`**: Redundant; key population is handled by direct SQL inserts or `setup_database.py`.

---