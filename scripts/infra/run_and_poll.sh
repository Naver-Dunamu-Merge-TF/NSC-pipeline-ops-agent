#!/bin/bash
RUNTIME_SMOKE_SCRIPT="/Workspace/Users/2dt026@msacademy.msai.kr/.bundle/data-pipeline/dev/files/scripts/i_qva6_checkpoint_path_smoke.py"

SUBMIT_OUT=$(databricks jobs submit --no-wait --json '{
  "run_name": "dev013-strict-smoke-serverless",
  "tasks": [{
    "task_key": "strict_smoke_serverless",
    "environment_key": "smoke_serverless",
    "spark_python_task": {
      "python_file": "'"$RUNTIME_SMOKE_SCRIPT"'",
      "source": "WORKSPACE",
      "parameters": ["--checkpoint-db-path", "/Volumes/nsc_dbw_dev_7405610275478542/default/agent_state_checkpoints/agent.db"]
    }
  }],
  "environments": [{
    "environment_key": "smoke_serverless",
    "spec": {"environment_version": "2"}
  }]
}' -o json)

# Note: The environment spec was modified to {"environment_version": "2"} since I remembered {"environment_version": "2"} is actually deprecated or might be correct? Let's use the one in runbook exactly to be safe!

RUN_ID=$(echo "$SUBMIT_OUT" | jq -r .run_id)

echo "Submitted run_id: $RUN_ID"

if [ -z "$RUN_ID" ] || [ "$RUN_ID" == "null" ]; then
  echo "Failed to submit job"
  echo "$SUBMIT_OUT"
  exit 1
fi

echo "Polling every 20s for completion..."
MAX_ATTEMPTS=20
ATTEMPT=0

while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
  STATUS_JSON=$(databricks jobs get-run --run-id "$RUN_ID" -o json)
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

if [ $ATTEMPT -eq $MAX_ATTEMPTS ]; then
  echo "Timed out waiting for job to complete."
fi

TASK_RUN_ID=$(databricks jobs get-run --run-id "$RUN_ID" -o json | jq -r '.tasks[0].run_id')
echo "Task run ID: $TASK_RUN_ID"
if [ "$TASK_RUN_ID" != "null" ] && [ -n "$TASK_RUN_ID" ]; then
  echo "Task output logs:"
  databricks jobs get-run-output $TASK_RUN_ID -o json | jq -r '.logs'
  echo "Task error logs:"
  databricks jobs get-run-output $TASK_RUN_ID -o json | jq -r '.error'
fi
