#!/bin/bash
# Host-side initialization script using brew-installed sqlcmd
echo "Waiting for SQL Server to accept connections..."
sleep 20

TOOL_PATH="/opt/homebrew/bin/sqlcmd"
if [ ! -f "$TOOL_PATH" ]; then
    TOOL_PATH="sqlcmd" # Setup path fallback
fi

echo "Running schema import..."
"$TOOL_PATH" -S localhost -U SA -P "0966288650aA@" -i data/SQLQuery1.sql

if [ $? -eq 0 ]; then
    echo "Database initialized successfully!"
else
    echo "Failed to initialize database. Check credentials or path."
fi
