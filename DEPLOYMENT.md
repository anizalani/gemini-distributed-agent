# Deploying the Gemini Distributed Agent to a New Host

This guide explains how to replicate the Gemini Distributed Agent on a new host. It assumes that the new host is on the same Tailnet as the original machine.

---

## 1. Prerequisites

Before you begin, ensure that the new host has the following software installed:

*   Git
*   Python 3
*   pip
*   Node.js and npm
*   PostgreSQL client (`psql`)

---

## 2. Deployment

We have created a `deploy.sh` script to automate the deployment process. 

1.  **Run the deployment script:**

    ```bash
    bash deploy.sh
    ```

    This script will perform the following actions:

    *   Clone the GitHub repository.
    *   Create a Python virtual environment.
    *   Install the required Python and Node.js dependencies.

2.  **Configure the database connection:**

    The deployment script will print instructions on how to create and configure the `.postgres.env` file. This file contains the credentials for connecting to the PostgreSQL database.

    *   **Copy the example file:**

        ```bash
        cp .postgres.env.example .postgres.env
        ```

    *   **Edit the file:**

        Open the `.postgres.env` file in a text editor and replace the placeholder values with your actual database credentials. Since your new host is on the same Tailnet, you can use the Tailnet IP address of your PostgreSQL server for the `POSTGRES_HOST` variable.

        ```
        POSTGRES_DB=postgres
        POSTGRES_USER=gemini_user
        POSTGRES_PASSWORD="your_password_here"
        POSTGRES_HOST=your_postgres_host_or_ip
        POSTGRES_PORT=5432
        ```

---

## 3. Post-Deployment

Once you have completed the deployment and configuration steps, you can start using the Gemini Distributed Agent on the new host. Refer to the `CONSOLIDATED_README.md` file for detailed usage instructions.

### Security Considerations

*   **`.postgres.env`:** This file contains sensitive database credentials. Make sure it is not committed to any version control system. The provided `.gitignore` file should already be configured to ignore this file.
*   **`llm_platform_config.json`:** This file may contain sensitive API keys. It is recommended to manage this file carefully and avoid committing it to version control if it contains private keys.
