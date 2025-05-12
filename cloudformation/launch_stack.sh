#!/bin/bash

# Check if tags file exists
if [ ! -f "cloudformation-tags.txt" ]; then
  echo "Error: cloudformation-tags.txt file not found"
  exit 1
fi

# Initialize tags variable
TAGS=""

# Read the tags file and construct the tags parameter
while IFS='=' read -r key value
do
  # Skip empty lines and comments
  if [[ ! -z "$key" && ! "$key" =~ ^[[:space:]]*# ]]; then
    # Append to tags string
    if [[ -z "$TAGS" ]]; then
      TAGS="Key=$key,Value=$value"
    else
      TAGS="$TAGS Key=$key,Value=$value"
    fi
  fi
done < cloudformation-tags.txt

aws cloudformation create-stack \
  --stack-name NGS360-GA4GHWES \
  --template-body file://cloudformation.yaml \
  --parameters file://cloudformation-parameters.json \
  --capabilities CAPABILITY_IAM \
  --tags $TAGS
