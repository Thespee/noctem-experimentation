#!/bin/bash
# Moltbot Signal Chat Handler (MVP)
# Receives Signal messages, sends to best available model, returns response
#
# Reads model from ~/.moltbot-model (written by optimizer.py)
# Falls back to "router" if not configured

MODEL_FILE="$HOME/.moltbot-model"
LOG_FILE="$HOME/moltbot-system/logs/signal-chat.log"

# These get set by quick-setup.sh or manually
SIGNAL_ACCOUNT="${SIGNAL_PHONE:-+1YOURPHONENUMBER}"
ALLOWED_NUMBER="${SIGNAL_PHONE:-+1YOURPHONENUMBER}"

# Ensure log directory exists
mkdir -p "$(dirname "$LOG_FILE")"

log() {
    echo "[$(date -Iseconds)] $1" >> "$LOG_FILE"
}

get_model() {
    if [[ -f "$MODEL_FILE" ]]; then
        cat "$MODEL_FILE"
    else
        echo "router"  # Fallback to small model
    fi
}

log "Signal chat handler started"
log "Using model: $(get_model)"
log "Signal account: $SIGNAL_ACCOUNT"

# Listen for incoming messages
signal-cli -a "$SIGNAL_ACCOUNT" receive --json 2>/dev/null | while read -r line; do
    # Skip empty lines
    [[ -z "$line" ]] && continue
    
    # Parse message
    sender=$(echo "$line" | jq -r '.envelope.source // empty' 2>/dev/null)
    message=$(echo "$line" | jq -r '.envelope.dataMessage.message // empty' 2>/dev/null)
    
    # Skip if no sender or message
    [[ -z "$sender" || -z "$message" ]] && continue
    
    log "FROM: $sender MSG: $message"
    
    # Only respond to allowed number
    if [[ "$sender" != "$ALLOWED_NUMBER" ]]; then
        log "BLOCKED: unauthorized sender $sender"
        continue
    fi
    
    # Get current best model
    MODEL=$(get_model)
    
    # Special commands
    case "$message" in
        "/status")
            response="Online. Model: $MODEL"
            ;;
        "/help")
            response="Commands: /status /model /help
Or just chat normally!"
            ;;
        "/model")
            response="Current model: $MODEL
Run 'python3 optimizer.py apply' on server to change."
            ;;
        *)
            # Send to Ollama
            log "Sending to Ollama ($MODEL)..."
            response=$(ollama run "$MODEL" "$message" 2>/dev/null)
            
            # Truncate if too long for Signal
            if [[ ${#response} -gt 2000 ]]; then
                response="${response:0:1997}..."
            fi
            
            # Handle empty response
            [[ -z "$response" ]] && response="(no response from model)"
            ;;
    esac
    
    log "RESPONSE: ${response:0:100}..."
    
    # Send response
    signal-cli -a "$SIGNAL_ACCOUNT" send -m "$response" "$sender" 2>/dev/null
    
done

log "Signal chat handler stopped"
