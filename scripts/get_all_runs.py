#!/usr/bin/env python3
import boto3
import datetime

OMICS_CLIENT = boto3.client('omics')

total_runs = 0
next_token = None

now = datetime.datetime.now(datetime.timezone.utc)
cutoff = now - datetime.timedelta(days=10)
runs_to_delete = []

while True:
    if next_token:
        response = OMICS_CLIENT.list_runs(
            startingToken=next_token,
            maxResults=100
        )
    else:
        response = OMICS_CLIENT.list_runs(
            maxResults=100
        )

    for run in response.get('items', []):
        # Dump the run details to a file
        print(run)

        # Decide if we want to keep the run
        status = run.get('status')
        created = run.get("creationTime")
        if status in ["COMPLETED", "FAILED", "CANCELLED"] and created < cutoff:
            runs_to_delete.append(run['id'])

        total_runs += 1

    next_token = response.get('nextToken')
    if not next_token:
        break

print(f"Total Runs: {total_runs}")

print(f"Runs to delete: {len(runs_to_delete)}")
for run_id in runs_to_delete:
    OMICS_CLIENT.delete_run(id=run_id)
