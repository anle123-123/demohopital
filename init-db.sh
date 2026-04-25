#!/bin/bash
# Wait for SQL Server to start
echo "Waiting for SQL Server to start..."
sleep 20

# Run the SQL script
echo "Running initialization script..."
/opt/mssql-tools/bin/sqlcmd -S localhost -U SA -P "0966288650aA@" -i data/SQLQuery1.sql

echo "Database initialized!"
