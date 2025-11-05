#!/bin/bash

# Move up one directory and activate the virtual environment
cd ..

echo "========================================="
echo "Soucing venv"
echo "========================================="

source venv/bin/activate



# Install dependencies
echo "========================================="
echo "Installing dependencies"
echo "========================================="
pip install -r requirements.txt

# Define experiment parameters
EXP_NAME="loss"
LOSS_RATES=(0.0 0.1 0.2 0.3 0.4 0.5)
PORT=50000
BIND_IP=127.0.0.1
SERVER_IP=127.0.0.1
DELAY=300
JITTER=300
PPS=30
DURATION=30
T_SKIP=2000

# Base output directory
BASE_DIR="experiment_data/${EXP_NAME}"
mkdir -p "$BASE_DIR"

# Loop over different loss rates
for LOSS in "${LOSS_RATES[@]}"; do
    echo "========================================="
    echo "Running experiment with ${EXP_NAME} = $LOSS"
    echo "========================================="

    # Create subdirectory for this loss rate
    EXP_DIR="${BASE_DIR}/${EXP_NAME}_${LOSS}"
    mkdir -p "$EXP_DIR"

    # Output file paths
    METRICS_FILE="${EXP_DIR}/metrics_${EXP_NAME}_${LOSS}.csv"
    RECEIVER_LOG="${EXP_DIR}/receiver_${EXP_NAME}_${LOSS}.log"
    SENDER_LOG="${EXP_DIR}/sender_${EXP_NAME}_${LOSS}.log"

    # Start the receiver in the background and record its PID
    python receiver.py \
        --bind $BIND_IP \
        --port $PORT \
        --metrics "$METRICS_FILE" \
        --t_skip $T_SKIP \
        > "$RECEIVER_LOG" 2>&1 &
    
    RECEIVER_PID=$!

    echo "Receiver started" 

    # Give the receiver a moment to start up
    sleep 2

    echo "Starting Sender" 
    # Start the sender (runs in foreground)
    python sender.py \
        --server $SERVER_IP \
        --port $PORT \
        --pps $PPS \
        --loss $LOSS \
        --delay $DELAY \
        --jitter $JITTER \
        --duration $DURATION \
        > "$SENDER_LOG" 2>&1

    echo "Sending finished"
    sleep 1

    # When sender finishes, stop the receiver
    echo "Stopping receiver (PID: $RECEIVER_PID)..."
    kill $RECEIVER_PID
    wait $RECEIVER_PID

    echo "Experiment with ${EXP_NAME}=$LOSS completed."
    echo "Results saved in $EXP_DIR"
    echo
done

# Deactivate virtual environment
deactivate

echo "All experiments finished. Results stored in $BASE_DIR"
