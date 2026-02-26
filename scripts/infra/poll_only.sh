#!/bin/bash
RUN_ID=$1
echo "Polling run_id: $RUN_ID"

MAX_ATTEMPTS=20
ATTEMPT=0

while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
  STATUS_JSON=$(databricks jobs get-run $RUN_ID -o json)
  STATE=$(echo "$STATUS_JSON" | jq -r .state.life_cycle_state)
  RESULT=$(echo "$STATUS_JSON" | jq -r .state.result_state)
  
  if [ "$STATE" == "TERMINATED" ] || [ "$STATE" == "INTERNAL_ERROR" ] || [ "$STATE" == "SKIPPED" ]; then
    echo "Job finished! Lifecycle: $STATE, Result: $RESULT"
    echo "State message: $(echo "$STATUS_JSON" | jq -r '.state.state_message')"
    break
  fi
  
  echo "Current state: $STATE... waiting 20 seconds. (Attempt $((ATTEMPT+1))/$MAX_ATTEMPTS)"
  sleep 20
  ATTEMPT=$((ATTEMPT+1))
done

TASK_RUN_ID=$(databricks jobs get-run $RUN_ID -o json | jq -r '.tasks[0].run_id')
echo "Task run ID: $TASK_RUN_ID"
if [ "$TASK_RUN_ID" != "null" ] && [ -n "$TASK_RUN_ID" ]; then
  echo "Task output logs:"
  databricks jobs get-run-output $TASK_RUN_ID -o json | jq -r '.logs'
  echo "Task error logs:"
  databricks jobs get-run-output $TASK_RUN_ID -o json | jq -r '.error'
fi
