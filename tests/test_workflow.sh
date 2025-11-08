#!/bin/bash

echo "--- QueueCTL Test Workflow ---"
set -e 

echo "🧹 Cleaning up old database and workers..."
rm -f ~/.queuectl/queue.db
rm -f ~/.queuectl/workers/*.pid
queuectl worker stop > /dev/null 2>&1 || true
sleep 1

echo "📦 Installing and initializing database..."
pip install . > /dev/null
queuectl init-db

echo "⚙️ Setting max_retries to 2..."
queuectl config set max_retries 2
queuectl config set backoff_base_seconds 1

echo "👷 Starting 2 workers in the background..."
queuectl worker start --count 2

echo "📬 Enqueuing jobs..."
queuectl enqueue '{"id":"job-success","command":"echo Hello from job-success"}'
queuectl enqueue '{"id":"job-fail-once","command":"(exit 1)"}'
queuectl enqueue '{"id":"job-invalid","command":"thiscommanddoesnotexist"}'

echo "⏳ Waiting 10 seconds for jobs to process and retry..."
sleep 10

echo "📊 Checking final status..."
queuectl status

echo "---"

echo "✅ Validating 'completed' queue..."
queuectl list --state completed
COMPLETED_JOBS=$(queuectl list --state completed)
if [[ ! "$COMPLETED_JOBS" == *"job-success"* ]]; then
    echo "❌ TEST FAILED: 'job-success' not found in completed jobs."
    exit 1
fi
echo "✔ 'job-success' completed as expected."

echo "---"

echo "✅ Validating Dead Letter Queue (DLQ)..."
queuectl dlq list
DLQ_JOBS=$(queuectl dlq list)
if [[ ! "$DLQ_JOBS" == *"job-fail-once"* ]]; then
    echo "❌ TEST FAILED: 'job-fail-once' not found in DLQ."
    exit 1
fi
if [[ ! "$DLQ_JOBS" == *"job-invalid"* ]]; then
    echo "❌ TEST FAILED: 'job-invalid' not found in DLQ."
    exit 1
fi
echo "✔ Failed jobs moved to DLQ as expected."

echo "---"
echo "🔁 Testing DLQ retry..."
queuectl dlq retry job-fail-once
sleep 3

echo "📊 Checking DLQ status after retry..."
queuectl dlq list
DLQ_JOBS_RETRY=$(queuectl dlq list)
if [[ ! "$DLQ_JOBS_RETRY" == *"job-fail-once"* ]]; then
    echo "❌ TEST FAILED: 'job-fail-once' did not return to DLQ after retry."
    exit 1
fi
echo "✔ 'job-fail-once' failed again and returned to DLQ."

echo "---"
echo "🛑 Stopping workers..."
queuectl worker stop

echo "---"
echo "🎉 All tests passed successfully! 🎉"