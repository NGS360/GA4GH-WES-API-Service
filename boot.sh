#!/bin/sh
# this script is used to boot a Docker container

echo "Initializing the database..."
while true; do
    flask db upgrade
    if [[ "$?" == "0" ]]; then
        break
    fi
    echo 'flask db upgrade' command failed, retrying in 5 secs...
    sleep 5
done

echo "Starting the application..."
python3 application.py
