# 🎨 Dashboard UI → API Mapping Guide

**For Complete Noobs: Which API provides which data on your screen!**

---

## 📺 What You See on Screen → Where It Comes From

This guide maps **EVERY element you see on the dashboard** to the **exact API and data field** that provides it.

---

## 🎯 Main API That Powers Everything

### **PRIMARY:** `GET /api/business/metrics`

**When called:** Every 1 second automatically  
**What it does:** Sends ALL the data you see on the Business tab

**Complete Response Structure:**
```json
{
  "business": {
    "pods": {
      "generation": {
        "no_of_generated": 5000000          ← Generated transactions
      },
      "prep": {
        "no_of_transformed": 3000000        ← Preprocessed transactions
      },
      "inference": {
        "fraud": 25000,                     ← Fraud detected
        "non_fraud": 4975000                ← Legitimate transactions
      }
    },
    "no_of_generated": 5000000,
    "no_of_processed": 5000000,
    "no_fraud": 25000
  },
  "kpis": {
    "1_fraud_exposure_identified": 1250000,
    "2_fraud_rate_percent": 0.5,
    "3_avg_transaction_value": 50.00,
    "4_decision_latency_ms": 12,
    "5_model_accuracy": 94.5,
    "6_false_positive_rate": 2.1,
    "7_cost_per_transaction": 0.0001,
    "8_total_cost_today": 500,
    "9_annual_savings_usd": 5000000,
    "10_throughput_per_second": 50000,
    "11_fraud_velocity_per_min": 1250
  },
  "fb": [
    {
      "read_mbps": 12000,
      "write_mbps": 18000,
      "util": 45,
      "throughput_mbps": 15000
    }
  ],
  "backlog": {
    "raw": 150000,
    "features": 50000,
    "results": 10000
  },
  "is_running": true,
  "elapsed_sec": 323.4
}
```

---

## 🔝 Top KPI Bar (Always Visible)

The orange/green bar at the very top of your screen.

### 1. 💰 Fraud Prevented

**UI Element:** Big dollar amount on the left  
**Example:** `$1.25M`

**Data Source:**
```
API: GET /api/business/metrics
Field: business.no_fraud × $50
Calculation: fraud_count × average_transaction_amount
```

**Code:**
```javascript
const fraudUsd = (b.no_fraud || 0) * 50;
document.getElementById('kpi-fraud-usd').textContent = '$' + (fraudUsd >= 1e3 ? (fraudUsd / 1e3).toFixed(0) + 'K' : fraudUsd);
```

### 2. 📊 Transactions Analyzed

**UI Element:** Number of transactions checked  
**Example:** `5.0M`

**Data Source:**
```
API: GET /api/business/metrics
Field: business.no_of_processed
```

**Code:**
```javascript
document.getElementById('kpi-txns-analyzed').textContent = fmtNum(txnsAnalyzed);
```

### 3. 🚨 High-Risk Transactions

**UI Element:** Red number showing fraud count  
**Example:** `25.0K`

**Data Source:**
```
API: GET /api/business/metrics
Field: business.no_fraud
```

**Code:**
```javascript
document.getElementById('kpi-high-risk').textContent = fmtNum(highRisk);
```

### 4. ⚡ Decision Latency

**UI Element:** Milliseconds to make a decision  
**Example:** `12ms`

**Data Source:**
```
API: GET /api/business/metrics
Field: kpis['4_decision_latency_ms']
```

**Code:**
```javascript
document.getElementById('kpi-decision-latency').textContent = latencyMs.toFixed(0) + 'ms';
```

### 5. 💵 Annual Savings

**UI Element:** Projected yearly savings  
**Example:** `$5.0M`

**Data Source:**
```
API: GET /api/business/metrics
Field: kpis['9_annual_savings_usd']
```

**Code:**
```javascript
document.getElementById('kpi-annual-savings').textContent = fmtUsd(annualSavings);
```

---

## ⏱️ Header Bar (Timer & Status)

### 6. ⏲️ Timer

**UI Element:** Running timer showing elapsed time  
**Example:** `05:23.4`

**Data Source:**
```
API: GET /api/business/metrics
Field: elapsed_sec
Calculation: Formats seconds into MM:SS.S
```

**Code:**
```javascript
document.getElementById('timer').textContent = fmtElapsed(elapsed);
// fmtElapsed converts 323.4 → "05:23.4"
```

### 7. 🔴 LIVE Indicator

**UI Element:** Red pulsing dot + "LIVE" text  
**Example:** `🔴 LIVE` or `⚫ STOPPED`

**Data Source:**
```
API: GET /api/business/metrics
Field: is_running (true/false)
```

**Code:**
```javascript
document.getElementById('live-text').textContent = running ? 'LIVE' : 'STOPPED';
```

---

## 📈 Business Tab

### 8. 📊 Fraud Exposure Identified

**UI Element:** Large card showing total fraud money  
**Example:** `$1.25M`

**Data Source:**
```
API: GET /api/business/metrics
Field: kpis['1_fraud_exposure_identified']
```

### 9. 📉 Fraud Rate

**UI Element:** Percentage of transactions that are fraud  
**Example:** `0.50%`

**Data Source:**
```
API: GET /api/business/metrics
Field: kpis['2_fraud_rate_percent']
```

### 10. 💳 Average Transaction Value

**UI Element:** Average dollar amount per transaction  
**Example:** `$50.00`

**Data Source:**
```
API: GET /api/business/metrics
Field: kpis['3_avg_transaction_value']
```

### 11. 🎯 Model Accuracy

**UI Element:** How accurate the AI model is  
**Example:** `94.5%`

**Data Source:**
```
API: GET /api/business/metrics
Field: kpis['5_model_accuracy']
```

### 12. ⚠️ False Positive Rate

**UI Element:** How often AI marks legit transactions as fraud  
**Example:** `2.1%`

**Data Source:**
```
API: GET /api/business/metrics
Field: kpis['6_false_positive_rate']
```

### 13. 💰 Cost Per Transaction

**UI Element:** Cost to check each transaction  
**Example:** `$0.0001`

**Data Source:**
```
API: GET /api/business/metrics
Field: kpis['7_cost_per_transaction']
```

### 14. 📅 Total Cost Today

**UI Element:** How much spent today on fraud detection  
**Example:** `$500`

**Data Source:**
```
API: GET /api/business/metrics
Field: kpis['8_total_cost_today']
```

### 15. ⚡ Throughput

**UI Element:** Transactions processed per second  
**Example:** `50,000/sec`

**Data Source:**
```
API: GET /api/business/metrics
Field: kpis['10_throughput_per_second']
```

### 16. 🚀 Fraud Velocity (IMPORTANT!)

**UI Element:** Badge showing fraud per minute  
**Example:** `▲ High: 1.25K/min` (red)  
or `Moderate: 450/min` (yellow)  
or `Low: 50/min` (green)

**Data Source:**
```
API: GET /api/business/metrics
Field: kpis['11_fraud_velocity_per_min']
```

**Code Logic:**
```javascript
if (fraudVelocity > 1000) {
  → Show RED "▲ High: X/min"
} else if (fraudVelocity > 100) {
  → Show YELLOW "Moderate: X/min"
} else {
  → Show GREEN "Low: X/min"
}
```

**What This Means:**
- **Velocity = Speed of fraud attempts**
- High velocity = Many fraud attempts happening fast!
- This is calculated from how many fraud transactions detected per minute

---

## ⚙️ Tech Tab (Technical View)

### 17. 📦 Data Generated

**UI Element:** Bar showing total transactions generated  
**Example:** `Generated: 5.0M txns`

**Data Source:**
```
API: GET /api/business/metrics
Field: business.pods.generation.no_of_generated
OR: business.no_of_generated
```

**Code:**
```javascript
const generated = gen.no_of_generated ?? b.no_of_generated ?? 0;
document.getElementById('tech-generated').textContent = fmtNum(generated) + ' txns';
```

### 18. ⚙️ Data Prep (CPU)

**UI Element:** Bar showing CPU preprocessing count  
**Example:** `Prep CPU: 2.0M` (40% of total prep)

**Data Source:**
```
API: GET /api/business/metrics
Field: business.pods.prep.no_of_transformed × 0.4
Calculation: Takes 40% of total prep (simulated CPU portion)
```

**Code:**
```javascript
const prepTotal = prep.no_of_transformed ?? 0;
document.getElementById('tech-prep-cpu').textContent = fmtNum(Math.floor(prepTotal * 0.4));
```

### 19. 🎮 Data Prep (GPU)

**UI Element:** Bar showing GPU preprocessing count  
**Example:** `Prep GPU: 3.0M` (60% of total prep)

**Data Source:**
```
API: GET /api/business/metrics
Field: business.pods.prep.no_of_transformed × 0.6
Calculation: Takes 60% of total prep (simulated GPU portion - faster!)
```

### 20. 💻 Inference (CPU)

**UI Element:** Bar showing CPU fraud checking count  
**Example:** `Inference CPU: 1.5M` (30% of total)

**Data Source:**
```
API: GET /api/business/metrics
Field: (business.pods.inference.fraud + business.pods.inference.non_fraud) × 0.3
Calculation: 30% of total inference on CPU
```

### 21. 🎮 Inference (GPU)

**UI Element:** Bar showing GPU fraud checking count  
**Example:** `Inference GPU: 3.5M` (70% of total)

**Data Source:**
```
API: GET /api/business/metrics
Field: (business.pods.inference.fraud + business.pods.inference.non_fraud) × 0.7
Calculation: 70% of total inference on GPU (much faster!)
```

### 22. 📋 Backlog

**UI Element:** Text showing queued transactions  
**Example:** `Backlog: 200K`

**Data Source:**
```
API: GET /api/business/metrics
Field: backlog.raw + backlog.features
Calculation: Combines raw transactions + features waiting
```

**Code:**
```javascript
const rawBacklog = (backlog.raw || 0) + (backlog.features || 0);
document.getElementById('tech-backlog').textContent = 'Backlog: ' + fmtNum(rawBacklog);
```

---

## 🗄️ FlashBlade Storage Metrics

### 23. 📥 Read Throughput

**UI Element:** FlashBlade read speed  
**Example:** `Read: 12.0 GB/s`

**Data Source:**
```
API: GET /api/business/metrics
Field: fb[last].read_mbps
Note: fb is an array, takes last element
```

**Code:**
```javascript
const fb = (data.fb && data.fb.length) ? data.fb[data.fb.length - 1] : {};
document.getElementById('fb-read').textContent = (fb.read_mbps ?? fb.throughput_mbps ?? 0).toFixed(1) + ' MB/s';
```

### 24. 📤 Write Throughput

**UI Element:** FlashBlade write speed  
**Example:** `Write: 18.0 GB/s`

**Data Source:**
```
API: GET /api/business/metrics
Field: fb[last].write_mbps
```

### 25. 📊 Storage Utilization

**UI Element:** Percentage bar showing FlashBlade usage  
**Example:** `Util: 45%` with colored bar

**Data Source:**
```
API: GET /api/business/metrics
Field: fb[last].util
```

**Code:**
```javascript
document.getElementById('fb-util').textContent = fbUtil + '%';
document.getElementById('fb-util-bar').style.width = Math.min(100, fbUtil) + '%';
```

---

## 📍 Generation Velocity Gauge (Speedometer!)

### 26. 🏎️ Generation Rate Gauge

**UI Element:** Half-circle gauge showing current generation speed  
**Example:** Needle pointing to `250K` (meaning 250K transactions in last 5 seconds)

**Data Source:**
```
API: GET /api/business/metrics
Field: business.pods.generation.no_of_generated
Calculation: 
  1. Remembers last count
  2. Subtracts: current - last = transactions generated since last check
  3. Multiplies by 5 (to show 5-second rate)
  4. Rotates gauge needle based on percentage of max (500K)
```

**Code:**
```javascript
// Dashboard polls every 1 second
const diff = Math.max(0, generated - window.lastGeneratedCount);
const rate5sec = diff * 5;  // Extrapolate to 5-second rate

// Update gauge
const maxGauge = 500000;  // Max is 500K/5sec (100K/sec)
const pct = Math.min(100, (rate5sec / maxGauge) * 100);
const deg = -45 + (pct * 1.8);  // -45° to 135° rotation
document.getElementById('gen-gauge-fill').style.transform = `rotate(${deg}deg)`;
```

**What This Means:**
- **Low reading (0-100K):** Slow generation, needle on left
- **Medium (100K-300K):** Normal speed, needle in middle
- **High (300K-500K):** Fast generation, needle on right
- This shows **real-time velocity** of data creation!

---

## 🎛️ Control Buttons (How to Start/Stop)

### 27. ▶️ Start Button

**What it does:** Starts the entire pipeline  
**UI Element:** Green "START PIPELINE" button (when stopped)

**API Called:**
```
POST /api/control/start
```

**What happens:**
1. You click button
2. Calls POST /api/control/start
3. Backend starts all pods
4. After 2-5 seconds, data starts flowing
5. All metrics start updating!

### 28. ⏸️ Stop Button

**What it does:** Stops the entire pipeline  
**UI Element:** Red "STOP PIPELINE" button (when running)

**API Called:**
```
POST /api/control/stop
```

**What happens:**
1. You click button
2. Calls POST /api/control/stop
3. All pods scale to 0 (stop)
4. Metrics stop updating
5. Timer stops

---

## 📊 Complete Data Flow Diagram

Here's how ALL the data flows from API to your screen:

```
┌─────────────────────────────────────────────────────────────────┐
│                  🌐 BACKEND SERVER (Port 8000)                   │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
           ┌───────────────────────────────────────┐
           │  GET /api/business/metrics            │
           │  (Called every 1 second automatically)│
           └───────────────────────────────────────┘
                               │
                               ▼
                 ┌─────────────────────────┐
                 │   JSON Response         │
                 │   (All the data!)       │
                 └─────────────────────────┘
                               │
         ┌─────────────────────┼───────────────────────┐
         │                     │                       │
         ▼                     ▼                       ▼
    ┌─────────┐          ┌─────────┐           ┌──────────┐
    │business│          │  kpis   │           │    fb    │
    │  .pods  │          │ object  │           │  array   │
    └─────────┘          └─────────┘           └──────────┘
         │                     │                       │
         ├─generation          ├─1_fraud_exposure      ├─[0].read_mbps
         │  └─no_of_generated  ├─2_fraud_rate          ├─[0].write_mbps
         │                     ├─3_avg_txn_value       └─[0].util
         ├─prep                ├─4_decision_latency
         │  └─no_of_transformed├─5_model_accuracy
         │                     ├─6_false_positive
         └─inference           ├─7_cost_per_txn
            ├─fraud            ├─8_total_cost
            └─non_fraud        ├─9_annual_savings
                               ├─10_throughput
                               └─11_fraud_velocity
                                          │
         ┌────────────────────────────────┴─────────────┐
         │                                              │
         ▼                                              ▼
  ┌─────────────────┐                        ┌──────────────────┐
  │  updateDashboard() │                      │updateBusinessMetrics()│
  │  JavaScript Func   │                      │  JavaScript Func     │
  └─────────────────┘                        └──────────────────┘
         │                                              │
         ▼                                              ▼
  document.getElementById('kpi-fraud-usd')      document.getElementById('kpi-fraud-rate')
  document.getElementById('timer')               document.getElementById('kpi-accuracy')
  document.getElementById('tech-generated')      ... and 20+ more elements
  ... updates 30+ UI elements!                   ... each gets updated!
```

---

## 🔄 Update Frequency

**How often does each UI element update?**

| UI Element | Update Frequency | API Called |
|------------|------------------|------------|
| Top KPI Bar (Fraud $, Txns, etc.) | Every 1 second | `/api/business/metrics` |
| Timer | Every 1 second | `/api/business/metrics` |
| LIVE indicator | Every 1 second | `/api/business/metrics` |
| Generation Gauge | Every 1 second | `/api/business/metrics` |
| Pipeline Progress Bars | Every 1 second | `/api/business/metrics` |
| FlashBlade Metrics | Every 1 second | `/api/business/metrics` |
| Fraud Velocity Badge | Every 1 second | `/api/business/metrics` |
| All Business Tab Metrics | Every 1 second | `/api/business/metrics` |

**Key Insight:** Everything updates from the SAME API call! This makes it super efficient.

---

## 💡 Special Calculated Fields

Some UI elements show **calculated** values, not direct API fields:

### 1. Fraud Prevented ($)
```
Source: business.no_fraud
Calculation: no_fraud × $50
Why: Assumes average transaction is $50
```

### 2. CPU/GPU Split
```
Source: business.pods.prep.no_of_transformed
Calculation: 
  - CPU: prepTotal × 0.4 (40%)
  - GPU: prepTotal × 0.6 (60%)
Why: Simulates realistic CPU/GPU workload distribution
```

### 3. Backlog
```
Source: backlog.raw + backlog.features
Calculation: Adds two queue depths
Why: Shows total transactions waiting to be processed
```

### 4. Generation Velocity (Gauge)
```
Source: business.pods.generation.no_of_generated
Calculation:
  1. currentCount - lastCount = diff
  2. diff × 5 = 5-second rate
  3. (rate / 500000) × 180° = needle angle
Why: Shows instantaneous generation speed
```

---

## 🎯 Summary: One API to Rule Them All!

**99% of your dashboard is powered by ONE API:**
```
GET /api/business/metrics
```

**This API returns:**
- ✅ All KPIs (top bar)
- ✅ All business metrics (Business tab)
- ✅ All pipeline progress (Tech tab)
- ✅ FlashBlade storage stats
- ✅ Queue backlogs
- ✅ Running status
- ✅ Elapsed time

**The dashboard:**
1. Calls this API every 1 second
2. Parses the JSON response
3. Updates 30+ UI elements
4. All charts, numbers, and gauges update smoothly!

**Other APIs are only for CONTROL:**
- `POST /api/control/start` ← Start button
- `POST /api/control/stop` ← Stop button
- `POST /api/control/scale/*` ← Scaling controls

---

## 🎓 Beginner Example: Tracing One Metric

Let's trace **Fraud Prevented** from start to finish:

```
1. BACKEND
   ├─ Inference pod detects 25,000 fraud transactions
   ├─ Writes to: /mnt/flashblade/.metrics.json
   │  {"total_fraud_blocked": 25000}
   └─ Backend reads this file

2. API
   ├─ Dashboard calls: GET /api/business/metrics
   └─ Backend responds:
      {
        "business": {
          "no_fraud": 25000
        }
      }

3. JAVASCRIPT
   ├─ updateDashboard(data) function runs
   ├─ Calculates: fraudUsd = 25000 × $50 = $1,250,000
   └─ Formats: "$1.25M"

4. UI
   └─ Updates element:
      document.getElementById('kpi-fraud-usd').textContent = "$1.25M"

5. SCREEN
   └─ You see: 💰 $1.25M in the top bar!
```

**This happens EVERY SECOND for EVERY metric!** 🔄

---

## 🚀 Pro Tips

1. **Open DevTools (F12)**: Watch the Network tab to see API calls in real-time!
2. **Look for `business/metrics` calls**: These happen every second
3. **Check the Response**: Click on a call to see the actual JSON data
4. **Compare to UI**: Match the JSON fields to what you see on screen

**Example:**
```
In Network tab:
  GET /api/business/metrics
  Response: {"business": {"no_fraud": 25000}}

On Screen:
  Top Bar shows: "25.0K High-Risk Transactions"
  
They match! 🎉
```

---

**Now you know EXACTLY where EVERY piece of data comes from!** 🎓
