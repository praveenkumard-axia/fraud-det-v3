# API Payload & Response Formats

Complete request/response specifications for all backend APIs.

---

## 📋 **API 1: Scale Pods**

### **Endpoint**
```
POST /api/control/scale/{pod_type}
```

### **Path Parameters**
```json
{
  "pod_type": "preprocessing" | "training" | "inference"
}
```

### **Request Payload**
```json
{
  "replicas": 5
}
```

**Field Specifications:**
- `replicas` (integer, required): Number of pod replicas
  - preprocessing: 1-10
  - training: 0-2
  - inference: 1-20

### **Success Response (200 OK)**
```json
{
  "success": true,
  "pod_type": "inference",
  "replicas": 5,
  "message": "Scaling request accepted"
}
```

### **Error Responses**

**Invalid Replicas (400 Bad Request)**
```json
{
  "success": false,
  "error": "Replicas must be between 1 and 20 for inference"
}
```

**Invalid Pod Type (400 Bad Request)**
```json
{
  "success": false,
  "error": "Invalid pod_type. Must be one of: preprocessing, training, inference"
}
```

**Missing Replicas (422 Unprocessable Entity)**
```json
{
  "detail": [
    {
      "loc": ["body", "replicas"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

### **cURL Examples**
```bash
# Scale inference to 10 pods
curl -X POST http://localhost:8000/api/control/scale/inference \
  -H "Content-Type: application/json" \
  -d '{"replicas": 10}'

# Scale preprocessing to 5 pods
curl -X POST http://localhost:8000/api/control/scale/preprocessing \
  -H "Content-Type: application/json" \
  -d '{"replicas": 5}'

# Scale training to 0 (pause training)
curl -X POST http://localhost:8000/api/control/scale/training \
  -H "Content-Type: application/json" \
  -d '{"replicas": 0}'
```

---

## 📋 **API 2: Set System Priority**

### **Endpoint**
```
POST /api/control/priority
```

### **Request Payload**
```json
{
  "priority": "inference"
}
```

**Field Specifications:**
- `priority` (string, required): System priority mode
  - Valid values: `"inference"`, `"training"`, `"balanced"`

### **Success Response (200 OK)**
```json
{
  "success": true,
  "priority": "inference",
  "message": "Priority updated"
}
```

### **Error Responses**

**Invalid Priority (400 Bad Request)**
```json
{
  "success": false,
  "error": "Invalid priority. Must be one of: inference, training, balanced"
}
```

**Missing Priority (422 Unprocessable Entity)**
```json
{
  "detail": [
    {
      "loc": ["body", "priority"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

### **Get Current Priority**

**Endpoint:** `GET /api/control/priority`

**Response (200 OK)**
```json
{
  "priority": "inference"
}
```

### **cURL Examples**
```bash
# Set priority to inference
curl -X POST http://localhost:8000/api/control/priority \
  -H "Content-Type: application/json" \
  -d '{"priority": "inference"}'

# Set priority to training
curl -X POST http://localhost:8000/api/control/priority \
  -H "Content-Type: application/json" \
  -d '{"priority": "training"}'

# Set priority to balanced
curl -X POST http://localhost:8000/api/control/priority \
  -H "Content-Type: application/json" \
  -d '{"priority": "balanced"}'

# Get current priority
curl http://localhost:8000/api/control/priority
```

---

## 📋 **API 3: Adjust Generation Rate**

### **Endpoint**
```
POST /api/control/throttle
```

### **Request Payload**
```json
{
  "rate": 25000
}
```

**Field Specifications:**
- `rate` (integer, required): Target generation rate in rows/second
  - Minimum: 1,000
  - Maximum: 100,000
  - Default: 50,000

### **Success Response (200 OK)**
```json
{
  "success": true,
  "rate": 25000,
  "message": "Generation rate updated"
}
```

### **Error Responses**

**Invalid Rate (400 Bad Request)**
```json
{
  "success": false,
  "error": "Rate must be between 1000 and 100000"
}
```

**Missing Rate (422 Unprocessable Entity)**
```json
{
  "detail": [
    {
      "loc": ["body", "rate"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

### **cURL Examples**
```bash
# Set rate to 25K rows/sec
curl -X POST http://localhost:8000/api/control/throttle \
  -H "Content-Type: application/json" \
  -d '{"rate": 25000}'

# Set rate to maximum (100K)
curl -X POST http://localhost:8000/api/control/throttle \
  -H "Content-Type: application/json" \
  -d '{"rate": 100000}'

# Set rate to minimum (1K)
curl -X POST http://localhost:8000/api/control/throttle \
  -H "Content-Type: application/json" \
  -d '{"rate": 1000}'
```

---

## 📋 **API 4: Dashboard Data**

### **Endpoint**
```
GET /api/dashboard
```

### **Request**
No payload required (GET request)

### **Success Response (200 OK)**
```json
{
  "pipeline": {
    "status": "running",
    "uptime_seconds": 3600,
    "current_stage": "inference"
  },
  "progress": {
    "data_ingestion": 100,
    "preprocessing": 100,
    "training": 100,
    "inference": 75
  },
  "utilization": {
    "cpu_cores": 4.2,
    "ram_percent": 45.3,
    "ram_gb": 12.5
  },
  "throughput": {
    "current": 45000,
    "peak": 52000,
    "unit": "rows/sec"
  },
  "business_metrics": {
    "total_transactions": 15000000,
    "fraud_detected": 1500,
    "fraud_rate": 0.01,
    "total_amount": 150000000.50,
    "fraud_amount": 500000.25
  },
  "queue_backlogs": {
    "raw_transactions": 125000,
    "features_ready": 50000,
    "inference_results": 10000,
    "training_queue": 0
  },
  "pod_counts": {
    "preprocessing": 2,
    "training": 1,
    "inference": 5
  },
  "system_config": {
    "generation_rate": 50000,
    "system_priority": "inference"
  }
}
```

**Field Descriptions:**

**pipeline:**
- `status` (string): Pipeline state - `"running"`, `"stopped"`, `"error"`
- `uptime_seconds` (integer): Seconds since pipeline started
- `current_stage` (string): Current active stage

**progress:**
- `data_ingestion` (integer): Progress percentage (0-100)
- `preprocessing` (integer): Progress percentage (0-100)
- `training` (integer): Progress percentage (0-100)
- `inference` (integer): Progress percentage (0-100)

**utilization:**
- `cpu_cores` (float): CPU cores in use
- `ram_percent` (float): RAM usage percentage
- `ram_gb` (float): RAM usage in GB

**throughput:**
- `current` (integer): Current throughput (rows/sec)
- `peak` (integer): Peak throughput (rows/sec)
- `unit` (string): Always `"rows/sec"`

**business_metrics:**
- `total_transactions` (integer): Total transactions processed
- `fraud_detected` (integer): Number of frauds detected
- `fraud_rate` (float): Fraud rate (0.0-1.0)
- `total_amount` (float): Total transaction amount ($)
- `fraud_amount` (float): Total fraud amount ($)

**queue_backlogs:**
- `raw_transactions` (integer): Messages in raw-transactions queue
- `features_ready` (integer): Messages in features-ready queue
- `inference_results` (integer): Messages in inference-results queue
- `training_queue` (integer): Messages in training queue

**pod_counts:**
- `preprocessing` (integer): Number of preprocessing pods
- `training` (integer): Number of training pods
- `inference` (integer): Number of inference pods

**system_config:**
- `generation_rate` (integer): Current generation rate (rows/sec)
- `system_priority` (string): Current priority mode

### **cURL Examples**
```bash
# Get all dashboard data
curl http://localhost:8000/api/dashboard

# Get specific field with jq
curl -s http://localhost:8000/api/dashboard | jq '.throughput.current'

# Get queue backlogs
curl -s http://localhost:8000/api/dashboard | jq '.queue_backlogs'

# Monitor continuously
watch -n 5 'curl -s http://localhost:8000/api/dashboard | jq .'
```

---

## 📋 **API 5: Queue Backlog Status**

### **Endpoint**
```
GET /api/backlog/status
```

### **Request**
No payload required (GET request)

### **Success Response (200 OK)**
```json
{
  "raw_transactions": 125000,
  "features_ready": 50000,
  "inference_results": 10000,
  "training_queue": 0,
  "timestamp": "2026-02-02T15:30:00Z"
}
```

**Field Descriptions:**
- `raw_transactions` (integer): Messages in raw-transactions queue
- `features_ready` (integer): Messages in features-ready queue
- `inference_results` (integer): Messages in inference-results queue
- `training_queue` (integer): Messages in training queue
- `timestamp` (string): ISO 8601 timestamp

### **cURL Examples**
```bash
# Get backlog status
curl http://localhost:8000/api/backlog/status

# Monitor specific queue
curl -s http://localhost:8000/api/backlog/status | jq '.raw_transactions'

# Watch backlog
watch -n 2 'curl -s http://localhost:8000/api/backlog/status | jq .'
```

---

## 📋 **API 6: Backlog Pressure & Alerts**

### **Endpoint**
```
GET /api/backlog/pressure
```

### **Request**
No payload required (GET request)

### **Success Response (200 OK) - Normal State**
```json
{
  "overall_pressure": "normal",
  "queues": {
    "raw_transactions": {
      "backlog": 125000,
      "threshold_warning": 500000,
      "threshold_critical": 1000000,
      "pressure_percent": 25.0,
      "status": "normal"
    },
    "features_ready": {
      "backlog": 50000,
      "threshold_warning": 250000,
      "threshold_critical": 500000,
      "pressure_percent": 20.0,
      "status": "normal"
    },
    "inference_results": {
      "backlog": 10000,
      "threshold_warning": 100000,
      "threshold_critical": 200000,
      "pressure_percent": 10.0,
      "status": "normal"
    }
  },
  "alerts": [],
  "recommendations": []
}
```

### **Success Response (200 OK) - High Pressure State**
```json
{
  "overall_pressure": "high",
  "queues": {
    "raw_transactions": {
      "backlog": 750000,
      "threshold_warning": 500000,
      "threshold_critical": 1000000,
      "pressure_percent": 75.0,
      "status": "warning"
    },
    "features_ready": {
      "backlog": 50000,
      "threshold_warning": 250000,
      "threshold_critical": 500000,
      "pressure_percent": 20.0,
      "status": "normal"
    },
    "inference_results": {
      "backlog": 10000,
      "threshold_warning": 100000,
      "threshold_critical": 200000,
      "pressure_percent": 10.0,
      "status": "normal"
    }
  },
  "alerts": [
    {
      "severity": "warning",
      "queue": "raw_transactions",
      "message": "Queue backlog above warning threshold",
      "backlog": 750000,
      "threshold": 500000,
      "timestamp": "2026-02-02T15:30:00Z"
    }
  ],
  "recommendations": [
    "Consider scaling up preprocessing pods",
    "Consider reducing generation rate"
  ]
}
```

### **Success Response (200 OK) - Critical State**
```json
{
  "overall_pressure": "critical",
  "queues": {
    "raw_transactions": {
      "backlog": 1200000,
      "threshold_warning": 500000,
      "threshold_critical": 1000000,
      "pressure_percent": 120.0,
      "status": "critical"
    }
  },
  "alerts": [
    {
      "severity": "critical",
      "queue": "raw_transactions",
      "message": "Queue backlog above critical threshold",
      "backlog": 1200000,
      "threshold": 1000000,
      "timestamp": "2026-02-02T15:30:00Z"
    }
  ],
  "recommendations": [
    "URGENT: Scale up preprocessing pods immediately",
    "URGENT: Reduce generation rate",
    "Consider pausing data generation temporarily"
  ]
}
```

**Field Descriptions:**

**overall_pressure:**
- Type: string
- Values: `"normal"`, `"medium"`, `"high"`, `"critical"`

**queues.{queue_name}:**
- `backlog` (integer): Current queue depth
- `threshold_warning` (integer): Warning threshold
- `threshold_critical` (integer): Critical threshold
- `pressure_percent` (float): Backlog as % of critical threshold
- `status` (string): `"normal"`, `"warning"`, `"critical"`

**alerts:**
- Array of alert objects
- `severity` (string): `"warning"` or `"critical"`
- `queue` (string): Queue name
- `message` (string): Alert description
- `backlog` (integer): Current backlog
- `threshold` (integer): Exceeded threshold
- `timestamp` (string): ISO 8601 timestamp

**recommendations:**
- Array of strings
- Actionable suggestions to resolve pressure

### **cURL Examples**
```bash
# Get pressure status
curl http://localhost:8000/api/backlog/pressure

# Check for alerts
curl -s http://localhost:8000/api/backlog/pressure | jq '.alerts'

# Get recommendations
curl -s http://localhost:8000/api/backlog/pressure | jq '.recommendations'

# Check overall pressure
curl -s http://localhost:8000/api/backlog/pressure | jq -r '.overall_pressure'
```

---

## 📋 **API 7: Start Pipeline**

### **Endpoint**
```
POST /api/control/start
```

### **Request**
No payload required

### **Success Response (200 OK)**
```json
{
  "success": true,
  "message": "Pipeline started",
  "timestamp": "2026-02-02T15:30:00Z"
}
```

### **Error Response (400 Bad Request)**
```json
{
  "success": false,
  "error": "Pipeline is already running"
}
```

### **cURL Example**
```bash
curl -X POST http://localhost:8000/api/control/start
```

---

## 📋 **API 8: Stop Pipeline**

### **Endpoint**
```
POST /api/control/stop
```

### **Request**
No payload required

### **Success Response (200 OK)**
```json
{
  "success": true,
  "message": "Pipeline stopped",
  "timestamp": "2026-02-02T15:30:00Z"
}
```

### **Error Response (400 Bad Request)**
```json
{
  "success": false,
  "error": "Pipeline is not running"
}
```

### **cURL Example**
```bash
curl -X POST http://localhost:8000/api/control/stop
```

---

## 📋 **API 9: Reset Telemetry**

### **Endpoint**
```
POST /api/control/reset
```

### **Request**
No payload required

### **Success Response (200 OK)**
```json
{
  "success": true,
  "message": "Telemetry reset",
  "timestamp": "2026-02-02T15:30:00Z"
}
```

### **cURL Example**
```bash
curl -X POST http://localhost:8000/api/control/reset
```

---

## 📋 **API 10: WebSocket Metrics Stream**

### **Endpoint**
```
WebSocket ws://localhost:8000/ws/metrics
```

### **Connection**
No initial payload required

### **Message Format (Server → Client)**

**Sent every 1 second (1 Hz)**

```json
{
  "timestamp": "2026-02-02T15:30:00Z",
  "throughput": {
    "current": 45000,
    "peak": 52000
  },
  "queue_backlogs": {
    "raw_transactions": 125000,
    "features_ready": 50000,
    "inference_results": 10000
  },
  "pod_counts": {
    "preprocessing": 2,
    "training": 1,
    "inference": 5
  },
  "utilization": {
    "cpu_cores": 4.2,
    "ram_percent": 45.3,
    "ram_gb": 12.5
  },
  "business_metrics": {
    "total_transactions": 15000000,
    "fraud_detected": 1500,
    "fraud_rate": 0.01
  }
}
```

### **JavaScript Example**
```javascript
const ws = new WebSocket('ws://localhost:8000/ws/metrics');

ws.onopen = () => {
  console.log('Connected to metrics stream');
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Metrics update:', data);
  
  // Update dashboard
  document.getElementById('throughput').textContent = data.throughput.current;
  document.getElementById('backlog').textContent = data.queue_backlogs.raw_transactions;
};

ws.onerror = (error) => {
  console.error('WebSocket error:', error);
};

ws.onclose = () => {
  console.log('Disconnected from metrics stream');
  // Reconnect logic
  setTimeout(() => {
    connectWebSocket();
  }, 5000);
};
```

### **Python Example**
```python
import websocket
import json

def on_message(ws, message):
    data = json.loads(message)
    print(f"Throughput: {data['throughput']['current']} rows/sec")
    print(f"Backlog: {data['queue_backlogs']['raw_transactions']}")

def on_error(ws, error):
    print(f"Error: {error}")

def on_close(ws, close_status_code, close_msg):
    print("Connection closed")

def on_open(ws):
    print("Connected to metrics stream")

ws = websocket.WebSocketApp(
    "ws://localhost:8000/ws/metrics",
    on_open=on_open,
    on_message=on_message,
    on_error=on_error,
    on_close=on_close
)

ws.run_forever()
```

### **CLI Examples**
```bash
# Using websocat
websocat ws://localhost:8000/ws/metrics

# Using wscat
wscat -c ws://localhost:8000/ws/metrics

# Using curl (HTTP upgrade)
curl -i -N \
  -H "Connection: Upgrade" \
  -H "Upgrade: websocket" \
  -H "Sec-WebSocket-Version: 13" \
  -H "Sec-WebSocket-Key: $(openssl rand -base64 16)" \
  http://localhost:8000/ws/metrics
```

---

## 📋 **API 11: Business Intelligence Metrics**

### **Endpoint**
```
GET /api/business/metrics
```

### **Request**
No payload required (GET request)

### **Success Response (200 OK)**
```json
{
  "fraud_exposure_identified": 247892.50,
  "fraud_rate": 0.0058,
  "alerts_per_million": 1946,
  "high_risk_txn_rate": 0.0019,
  "projected_annual_savings": 128000000,
  
  "risk_score_distribution": [
    { "bin": "0-5", "count": 450000, "percentage": 6.8, "score": 80 },
    { "bin": "5-10", "count": 420000, "percentage": 6.4, "score": 75 },
    { "bin": "10-15", "count": 380000, "percentage": 5.8, "score": 70 }
  ],
  
  "fraud_velocity": [
    { "timestamp": "2026-02-04T13:21:00Z", "time": "-30m", "count": 45, "score": 99 },
    { "timestamp": "2026-02-04T13:22:00Z", "time": "-29m", "count": 42, "score": 95 },
    { "timestamp": "2026-02-04T13:23:00Z", "time": "-28m", "count": 50, "score": 98 }
  ],
  
  "risk_signals_by_category": [
    { "category": "shopping_net", "amount": 68240.50, "count": 842, "score": 87 },
    { "category": "grocery_pos", "amount": 48120.75, "count": 612, "score": 82 },
    { "category": "misc_net", "amount": 37450.20, "count": 489, "score": 79 }
  ],
  
  "recent_risk_signals": [
    {
      "risk_score": 97.8,
      "merchant": "fraud_Kiehn LLC",
      "category": "shopping_net",
      "cc_num_masked": "***4095",
      "state": "TX",
      "cardholder": "Jennifer B.",
      "amount": 1842.30,
      "timestamp": "2026-02-04T13:51:38Z",
      "seconds_ago": 2
    },
    {
      "risk_score": 95.2,
      "merchant": "fraud_Rippin, Kub and Mann",
      "category": "misc_net",
      "cc_num_masked": "***2095",
      "state": "CA",
      "cardholder": "Edward S.",
      "amount": 946.77,
      "timestamp": "2026-02-04T13:51:32Z",
      "seconds_ago": 8
    }
  ],
  
  "ml_details": {
    "precision": 0.942,
    "recall": 0.897,
    "accuracy": 0.989,
    "threshold": 11,
    "decision_latency_ms": 12.4
  },
  
  "risk_concentration": {
    "top_1_percent_txns": 12847,
    "top_1_percent_fraud_amount": 168567.80,
    "total_fraud_amount": 247892.50,
    "concentration_percentage": 68.0,
    "pattern_alert": "shopping_net + misc_net (44%)"
  },
  
  "state_risk": [
    { "rank": 1, "state": "TX", "fraud_amount": 38420.50, "count": 487 },
    { "rank": 2, "state": "CA", "fraud_amount": 34190.25, "count": 432 },
    { "rank": 3, "state": "NY", "fraud_amount": 28770.80, "count": 365 }
  ],
  
  "metadata": {
    "total_transactions": 6600000,
    "high_risk_count": 12847,
    "threshold": 75,
    "elapsed_hours": 2.0,
    "timestamp": "2026-02-04T13:51:40Z"
  }
}
```

### **Field Descriptions**

**Top-Level Metrics:**
- `fraud_exposure_identified` (float): Total $ amount flagged as fraud (risk_score ≥ 11)
  - Formula: `SUM(amt) WHERE risk_score ≥ 11`
- `fraud_rate` (float): Percentage of total amount flagged as fraud
  - Formula: `SUM(amt flagged) / SUM(amt total)`
- `alerts_per_million` (integer): Number of alerts per 1M transactions
  - Formula: `(flagged / total) × 1,000,000`
- `high_risk_txn_rate` (float): Percentage of transactions flagged as high-risk
  - Formula: `COUNT(flagged) / COUNT(total)`
- `projected_annual_savings` (float): Estimated annual fraud prevention savings
  - Formula: `(fraud_exposure / hours_elapsed) × 8,760`

**risk_score_distribution:**
- Array of 20 bins (0-5, 5-10, ..., 95-100)
- `bin` (string): Score range
- `count` (integer): Number of transactions in this bin
- `percentage` (float): Percentage of total transactions
- `score` (integer): Visualization height (0-100)

**fraud_velocity:**
- Array of 30 data points (last 30 minutes)
- `timestamp` (string): ISO 8601 timestamp
- `time` (string): Relative time label (e.g., "-30m", "-29m")
- `count` (integer): Number of high-risk transactions in this minute
- `score` (integer): Visualization height (0-100)

**risk_signals_by_category:**
- Array of transaction categories sorted by fraud amount
- `category` (string): Transaction category name
- `amount` (float): Total fraud amount for this category
- `count` (integer): Number of fraudulent transactions
- `score` (integer): Average risk score for visualization

**recent_risk_signals:**
- Array of most recent high-risk transactions (last 60 seconds, limit 10)
- `risk_score` (float): Model risk score (0-100)
- `merchant` (string): Merchant name
- `category` (string): Transaction category
- `cc_num_masked` (string): Masked credit card number
- `state` (string): US state code
- `cardholder` (string): Cardholder name (first name + last initial)
- `amount` (float): Transaction amount
- `timestamp` (string): ISO 8601 timestamp
- `seconds_ago` (integer): Seconds since transaction

**ml_details:**
- `precision` (float): TP / (TP + FP)
- `recall` (float): TP / (TP + FN)
- `accuracy` (float): (TP + TN) / (TP + TN + FP + FN)
- `threshold` (integer): Decision threshold (default: 11)
- `decision_latency_ms` (float): Average decision latency in milliseconds

**risk_concentration:**
- `top_1_percent_txns` (integer): Number of transactions in top 1%
- `top_1_percent_fraud_amount` (float): Fraud amount from top 1%
- `total_fraud_amount` (float): Total fraud amount
- `concentration_percentage` (float): Percentage of fraud from top 1%
- `pattern_alert` (string): Detected fraud pattern

**state_risk:**
- Array of top 8 states by fraud amount
- `rank` (integer): State ranking (1-8)
- `state` (string): US state code
- `fraud_amount` (float): Total fraud amount for this state
- `count` (integer): Number of fraudulent transactions

**metadata:**
- `total_transactions` (integer): Total transactions processed
- `high_risk_count` (integer): Number of high-risk transactions
- `threshold` (integer): Risk score threshold
- `elapsed_hours` (float): Hours since pipeline started
- `timestamp` (string): ISO 8601 timestamp of response

### **KPI Calculation Formulas**

| # | KPI | Formula | Fields Used |
|---|-----|---------|-------------|
| 1 | Fraud Exposure Identified | `SUM(amt) WHERE risk_score ≥ 11` | amt, model output |
| 2 | Transactions Analyzed | `COUNT(*)` | all rows |
| 3 | High-Risk Flagged | `COUNT(*) WHERE risk_score ≥ 11` | model output |
| 4 | Decision Latency | `AVG(t_output − t_input)` | pipeline timestamps |
| 5 | Precision @ Threshold | `TP / (TP + FP)` | is_fraud, model output |
| 6 | Fraud Rate | `SUM(amt flagged) / SUM(amt total)` | amt, model output |
| 7 | Alerts per 1M | `(flagged / total) × 1,000,000` | model output |
| 8 | High-Risk Txn Rate | `COUNT(flagged) / COUNT(total)` | model output |
| 9 | Annual Savings | `(fraud_exposure / hours_elapsed) × 8,760` | amt, time |
| 10 | Risk Distribution | `GROUP BY risk_score bins` | model output |
| 11 | Fraud Velocity | `COUNT(flagged) GROUP BY minute` | model output, time |
| 12 | Category Risk | `SUM(amt flagged) GROUP BY category` | category, amt |
| 13 | Risk Concentration | `SUM(amt top 1%) / SUM(amt flagged)` | amt, model output |
| 14 | State Risk | `SUM(amt flagged) GROUP BY state` | state, amt |
| 15 | Recall | `TP / (TP + FN)` | is_fraud, model output |
| 16 | False Positive Rate | `FP / (FP + TN)` | is_fraud, model output |

### **cURL Examples**
```bash
# Get all business metrics
curl http://localhost:8000/api/business/metrics

# Get specific metric with jq
curl -s http://localhost:8000/api/business/metrics | jq '.fraud_exposure_identified'

# Get ML details
curl -s http://localhost:8000/api/business/metrics | jq '.ml_details'

# Get recent alerts
curl -s http://localhost:8000/api/business/metrics | jq '.recent_risk_signals'

# Monitor continuously
watch -n 5 'curl -s http://localhost:8000/api/business/metrics | jq .'
```

### **JavaScript Example**
```javascript
// Fetch business metrics
async function fetchBusinessMetrics() {
  const response = await fetch('/api/business/metrics');
  const data = await response.json();
  
  // Update dashboard
  document.getElementById('fraud-exposure').textContent = 
    '$' + formatNumber(data.fraud_exposure_identified);
  
  document.getElementById('fraud-rate').textContent = 
    (data.fraud_rate * 100).toFixed(2) + '%';
  
  document.getElementById('precision').textContent = 
    (data.ml_details.precision * 100).toFixed(1) + '%';
  
  // Update charts
  updateRiskDistribution(data.risk_score_distribution);
  updateFraudVelocity(data.fraud_velocity);
  updateCategoryRisk(data.risk_signals_by_category);
  updateRecentAlerts(data.recent_risk_signals);
}

// Poll every 5 seconds
setInterval(fetchBusinessMetrics, 5000);
```

---

## 📊 **Quick Reference Table**

| API | Method | Payload Required | Response Type |
|-----|--------|------------------|---------------|
| Scale Pods | POST | ✅ Yes | JSON |
| Set Priority | POST | ✅ Yes | JSON |
| Throttle Rate | POST | ✅ Yes | JSON |
| Dashboard | GET | ❌ No | JSON |
| Backlog Status | GET | ❌ No | JSON |
| Backlog Pressure | GET | ❌ No | JSON |
| Start Pipeline | POST | ❌ No | JSON |
| Stop Pipeline | POST | ❌ No | JSON |
| Reset Telemetry | POST | ❌ No | JSON |
| Metrics Stream | WebSocket | ❌ No | JSON Stream |

---

## 🔧 **Common Error Codes**

| Code | Meaning | Example |
|------|---------|---------|
| 200 | Success | Request completed successfully |
| 400 | Bad Request | Invalid parameters or state |
| 422 | Unprocessable Entity | Missing required fields |
| 500 | Internal Server Error | Server-side error |

---

## 📝 **Testing Script**

```bash
#!/bin/bash
# Test all APIs

BASE_URL="http://localhost:8000"

echo "=== Testing Backend APIs ==="

# 1. Scale inference
echo -e "\n1. Scale inference to 5 pods"
curl -X POST $BASE_URL/api/control/scale/inference \
  -H "Content-Type: application/json" \
  -d '{"replicas": 5}'

# 2. Set priority
echo -e "\n\n2. Set priority to training"
curl -X POST $BASE_URL/api/control/priority \
  -H "Content-Type: application/json" \
  -d '{"priority": "training"}'

# 3. Throttle rate
echo -e "\n\n3. Set rate to 25K"
curl -X POST $BASE_URL/api/control/throttle \
  -H "Content-Type: application/json" \
  -d '{"rate": 25000}'

# 4. Dashboard
echo -e "\n\n4. Get dashboard data"
curl -s $BASE_URL/api/dashboard | jq '.throughput'

# 5. Backlog status
echo -e "\n\n5. Get backlog status"
curl -s $BASE_URL/api/backlog/status | jq .

# 6. Backlog pressure
echo -e "\n\n6. Get backlog pressure"
curl -s $BASE_URL/api/backlog/pressure | jq '.overall_pressure'

# 7. Start pipeline
echo -e "\n\n7. Start pipeline"
curl -X POST $BASE_URL/api/control/start

# 8. Stop pipeline
echo -e "\n\n8. Stop pipeline"
curl -X POST $BASE_URL/api/control/stop

# 9. Reset telemetry
echo -e "\n\n9. Reset telemetry"
curl -X POST $BASE_URL/api/control/reset

echo -e "\n\n=== All tests complete ==="
```

---

**Document Version:** 1.0  
**Last Updated:** 2026-02-02  
**Total APIs:** 10 (9 REST + 1 WebSocket)
