#!/usr/bin/env python3
"""
Pod 4: Inference Client (Verification)
Uses Triton Client to send requests to the inference server.
"""

import sys
import time
import psutil
import numpy as np
import tritonclient.http as httpclient
from tritonclient.utils import InferenceServerException

def main():
    url = "localhost:8000"
    model_name = "fraud_xgboost"
    
    try:
        triton_client = httpclient.InferenceServerClient(url=url, verbose=False)
    except Exception as e:
        print(f"Failed to create client: {e}")
        sys.exit(1)
        
    if not triton_client.is_server_live():
        print("Server is not live")
        sys.exit(1)
        
    print("Server is live")
    
    # Generate dummy data matching the feature size (20 features)
    batch_size = 1
    input_data = np.random.randn(batch_size, 20).astype(np.float32)
    
    inputs = [
        httpclient.InferInput("input__0", input_data.shape, "FP32")
    ]
    inputs[0].set_data_from_numpy(input_data)
    
    outputs = [
        httpclient.InferRequestedOutput("output__0")
    ]
    
    try:
        start = time.time()
        result = triton_client.infer(model_name, inputs, outputs=outputs)
        end = time.time()
        
        cpu = psutil.cpu_percent()
        cpu_cores = (cpu / 100.0) * psutil.cpu_count()
        mem = psutil.virtual_memory()
        mem_gb = mem.used / (1024 ** 3)

        print(f"Inference result: {result.as_numpy('output__0')}")
        print(f"METRICS: Latency={(end-start)*1000:.2f} ms | CPU={cpu_cores:.1f} Cores | RAM={mem.percent:.1f}% ({mem_gb:.2f} GB)")
        
    except InferenceServerException as e:
        print(f"Inference failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
