# Gemini Distributed Agent

The Gemini Distributed Agent is a powerful, database-backed system for running Google's Gemini model in a persistent, multi-agent environment. It features a relational database for logging, Redis caching for performance, and a web UI for real-time monitoring.

---

## ✨ Features

- **Agentic & Interactive Modes**: Run the agent in fully autonomous mode (`--agentic`) or have it request confirmation before executing commands (`--interactive`).
- **Relational Database Backend**: All actions are logged to a PostgreSQL database, providing a complete audit trail.
    - `tasks`: High-level information about each task.
    - `interactions`: A complete history of every prompt and response.
    - `command_log`: A log of every command the agent attempts to execute.
    - `api_keys`: Manages the status and usage of all API keys.
- **Redis Caching**: API key availability is cached in Redis to minimize database queries and improve performance.
- **Web UI for Monitoring**: A built-in Flask web application provides a real-time view into the agent's operations.
    - **Usage Logs**: View the `usage_log` table.
    - **Tasks**: View the `tasks` table.
    - **API Keys**: Monitor the status of all API keys.
    - **Interactions**: See the full conversation history for all tasks.
    - **Command Log**: Review every command the agent has run.

---

## 🚀 Setup & Installation

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
    ```

4.  **Configure Environment Variables**
    - Copy `.env.example` to `.env` and fill in the values.
    - Copy `.postgres.env.example` to `.postgres.env` and fill in your database credentials.

---

## Usage

### Running the Agent

The agent is run using the `gemma` command, which is an alias for the `gemini_agent.py` script.

```bash
gemma [PROMPT] [OPTIONS]
```

**Example:**
```bash
gemma "Refactor the web_ui.py script to use websockets." --agentic --permissions superuser
```

**Arguments & Options:**

| Argument      | Description                                                                                             |
|---------------|---------------------------------------------------------------------------------------------------------|
| `prompt`      | The initial prompt or instruction for the agent. Can be a string or a path to a file.                   |
| `--interactive` | If set, the agent will ask for confirmation before executing any shell commands.                        |
| `--agentic`     | If set, the agent will run autonomously until the task is complete or it encounters an error.           |
| `--permissions` | Sets the permission level for command execution. Can be `weak` (default) or `superuser`.              |
| `--task-id`     | The specific task ID to resume. If not provided, a new task ID is generated.                            |

### Running the Web UI

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
    Open your web browser and navigate to `http://<your-server-ip>:5002`.
