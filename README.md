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
        "gemini-cli-aniz-2": "YOUR_API_KEY_HERE",
        ...
    },
    "openai": {
        "api_key": "YOUR_OPENAI_API_KEY"
    },
    ...
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
