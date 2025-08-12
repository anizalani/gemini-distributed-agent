#!/bin/bash

# This script launches the Gemini interactive wrapper using an absolute path
# to the correct Python executable from the virtual environment, which ensures
# all dependencies are loaded correctly.

PYTHON_EXEC="/opt/gemini-distributed-agent/venv/bin/python"
GEMINI_WRAPPER="/opt/gemini-distributed-agent/gemini_interactive_wrapper.py"

if [ ! -f "$PYTHON_EXEC" ]; then
  echo "Error: The specified Python executable does not exist: $PYTHON_EXEC" >&2
  exit 1
fi

echo "Launching Gemini interactive wrapper with virtual environment..."

# Execute the Python wrapper with the virtual environment's Python.
$PYTHON_EXEC $GEMINI_WRAPPER "$@"

EXIT_CODE=$?
if [[ $EXIT_CODE -ne 0 ]]; then
    echo "The interactive wrapper exited with code $EXIT_CODE."
fi
