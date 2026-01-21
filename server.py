import os
import subprocess
import threading
import json
import asyncio
from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

app = FastAPI(title="Spearhead.so Fraud Detection Controller")

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Shared state
class PipelineState:
    def __init__(self):
        self.is_running = False
        self.logs = []
        self.queue = asyncio.Queue()
        self.stage_peaks = {} # Track peak throughput per stage

state = PipelineState()
BASE_DIR = Path(__file__).parent
STATS_FILE = BASE_DIR / "stats.json"

async def log_generator():
    """Streams logs from the queue to the client via SSE."""
    # Send existing logs first? (Optional)
    while True:
        try:
            log_line = await state.queue.get()
            yield f"data: {json.dumps({'message': log_line})}\n\n"
            if log_line == "___PIPELINE_COMPLETE___":
                break
        except asyncio.CancelledError:
            break

def run_pipeline_sync(stage="all"):
    """Runs the pipeline script and captures output."""
    state.is_running = True
    state.logs = []
    state.stage_peaks = {} # Reset peaks for new run
    
    # Environment for the process
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    
    cmd = ["/home/anuj/Axia/myenv/bin/python", "run_pipeline.py", "--stage", stage]
    
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        cwd=str(BASE_DIR)
    )

    for line in iter(process.stdout.readline, ''):
        line = line.strip()
        if line:
            # Put in queue using thread-safe method
            asyncio.run_coroutine_threadsafe(state.queue.put(line), loop)
    
    process.wait()
    state.is_running = False
    asyncio.run_coroutine_threadsafe(state.queue.put("___PIPELINE_COMPLETE___"), loop)

@app.get("/")
def read_root():
    return {"status": "Spearhead.so Controller is Online"}

@app.post("/run")
async def start_pipeline(background_tasks: BackgroundTasks, stage: str = "all"):
    if state.is_running:
        return {"status": "error", "message": "Pipeline is already running"}
    
    # Clear queue
    while not state.queue.empty():
        state.queue.get_nowait()
        
    background_tasks.add_task(run_pipeline_sync, stage)
    return {"status": "success", "message": f"Pipeline stage {stage} started"}

@app.get("/stream")
async def stream_logs():
    return StreamingResponse(log_generator(), media_type="text/event-stream")

@app.get("/stats")
async def get_stats():
    if STATS_FILE.exists():
        try:
            with open(STATS_FILE) as f:
                data = json.load(f)
                
                # Update peak throughput logic
                stage = data.get("stage", "Unknown")
                current_t = data.get("throughput", 0)
                
                if stage not in state.stage_peaks:
                    state.stage_peaks[stage] = 0
                
                if current_t > state.stage_peaks[stage]:
                    state.stage_peaks[stage] = current_t
                
                # If current is 0 (pod finished or idle), return the peak for that stage
                if current_t == 0 and stage in state.stage_peaks:
                    data["throughput"] = state.stage_peaks[stage]
                
                return data
        except:
            return {"error": "Could not read stats"}
    return {"error": "Stats file not found"}

# Capture the event loop for the background thread
loop = None

@app.on_event("startup")
async def startup_event():
    global loop
    loop = asyncio.get_running_loop()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
