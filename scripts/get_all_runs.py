#!/usr/bin/env python3
import boto3

OMICS_CLIENT = boto3.client('omics')

total_runs = 0
next_token = None
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
        total_runs += 1

    next_token = response.get('nextToken')
    if not next_token:
        break

print(f"Total Runs: {total_runs}")
