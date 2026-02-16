
import sys
from pathlib import Path
from typing import Optional, Dict, Any

def parse_telemetry_line(line: str) -> Optional[Dict]:
    """Parse [TELEMETRY] log line from pod output"""
    if "[TELEMETRY]" not in line:
        return None
    
    try:
        # Extract key=value pairs
        data = {}
        parts = line.split("|")
        for part in parts:
            part = part.strip()
            # Remove [TELEMETRY] tag if present in this part (usually the first one)
            part = part.replace("[TELEMETRY]", "").strip()
            
            if "=" in part:
                key, value = part.split("=", 1)
                key = key.strip()
                value = value.strip()
                
                if key in ["stage", "status"]:
                    data[key] = value
                elif key in ["rows", "throughput", "fraud_blocked"]:
                    data[key] = int(value)
                elif key in ["elapsed", "cpu_cores", "ram_gb", "ram_percent"]:
                    data[key] = float(value)
        
        return data
    except Exception as e:
        print(f"Failed to parse telemetry: {e}")
        return None

test_line = "stage=Ingest | status=Running | rows=530000 | throughput=22595 | elapsed=23.5 | cpu_cores=10.8 | ram_gb=10.74 | ram_percent=70.0"
# Add [TELEMETRY] tag like the pod does
full_line = "[TELEMETRY] " + test_line

result = parse_telemetry_line(full_line)
print(f"Result: {result}")
