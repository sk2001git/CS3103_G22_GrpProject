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
EXP_NAME="jitter"
LOSS_RATE=0.2
PORT=50000
BIND_IP=127.0.0.1
SERVER_IP=127.0.0.1
DELAY=300
JITTERS=(10 50 100 200 400 800)
PPS=30
DURATION=30
T_SKIP=$(( DURATION * 1000 ))

# Base output directory
BASE_DIR="experiment_data/${EXP_NAME}"
mkdir -p "$BASE_DIR"

# Loop over different loss rates
for JITTER in "${JITTERS[@]}"; do
    echo "========================================="
    echo "Running experiment with ${EXP_NAME} = $JITTER"
    echo "========================================="

    # Create subdirectory for this loss rate
    EXP_DIR="${BASE_DIR}/${EXP_NAME}_${JITTER}"
    mkdir -p "$EXP_DIR"

    # Output file paths
    RECEIVER_METRICS_FILE="${EXP_DIR}/receiver_metrics_${EXP_NAME}_${JITTER}.csv"
    SENDER_METRICS_FILE="${EXP_DIR}/sender_metrics_${EXP_NAME}_${JITTER}.csv"
    RECEIVER_LOG="${EXP_DIR}/receiver_${EXP_NAME}_${JITTER}.log"
    SENDER_LOG="${EXP_DIR}/sender_${EXP_NAME}_${JITTER}.log"

    # Start the receiver in the background and record its PID
    python receiver.py \
        --bind $BIND_IP \
        --port $PORT \
        --metrics "$RECEIVER_METRICS_FILE" \
        --t_skip $T_SKIP \
        > "$RECEIVER_LOG" 2>&1 &
    
    RECEIVER_PID=$!

    echo "Receiver started" 

    # Give the receiver a moment to start up
    sleep 1

    echo "Starting Sender" 
    # Start the sender (runs in foreground)
    python sender.py \
        --server $SERVER_IP \
        --port $PORT \
        --pps $PPS \
        --loss $LOSS_RATE \
        --delay $DELAY \
        --jitter $JITTER \
        --duration $DURATION \
        --metrics $SENDER_METRICS_FILE \
        > "$SENDER_LOG" 2>&1
    
    echo "Sending finished"
    sleep 2

    # When sender finishes, stop the receiver
    echo "Stopping receiver (PID: $RECEIVER_PID)..."
    kill $RECEIVER_PID
    wait $RECEIVER_PID

    PID=$(lsof -t -i :$PORT)
    if [ -n "$PID" ]; then
        echo "Port $PORT is in use by PID $PID. Killing it..."
        kill -9 $PID
        sleep 1
    else
        echo "Port $PORT is free."
    fi

    sleep 2
    echo "Experiment with ${EXP_NAME}=$JITTER completed."
    echo "Results saved in $EXP_DIR"
    echo
done

# Deactivate virtual environment
deactivate

echo "All experiments finished. Results stored in $BASE_DIR"

echo "Calculating metrics"

python plot_experiment_metrics.py --EXP_NAME=$EXP_NAME --BASE_DIR=$BASE_DIR

echo "Calculation completed"