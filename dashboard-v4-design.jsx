import React, { useState } from 'react';

export default function DashboardV4Design() {
  const [cpuPrepPods, setCpuPrepPods] = useState(1);
  const [gpuPrepPods, setGpuPrepPods] = useState(1);
  const [cpuInferPods, setCpuInferPods] = useState(1);
  const [gpuInferPods, setGpuInferPods] = useState(1);
  const [generatorSpeed, setGeneratorSpeed] = useState(50);

  return (
    <div className="min-h-screen bg-slate-950 text-white p-4 font-sans">
      {/* Header */}
      <div className="bg-slate-900 rounded-lg p-4 mb-4 flex justify-between items-center border border-slate-800">
        <div className="flex items-center gap-4">
          <div className="w-10 h-10 bg-orange-500 rounded flex items-center justify-center font-bold text-xl">P</div>
          <div>
            <div className="font-semibold text-lg">Pure Storage</div>
            <div className="text-sm text-slate-400">AI Fraud Detection Pipeline Demo</div>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <div className="px-3 py-1.5 bg-slate-800 rounded text-sm border border-slate-700">FlashBlade</div>
          <div className="px-3 py-1.5 bg-slate-800 rounded text-sm border border-slate-700">NVIDIA L40S</div>
          <div className="flex items-center gap-2 px-4 py-1.5 bg-red-500/20 border border-red-500/50 rounded">
            <div className="w-2 h-2 bg-red-500 rounded-full animate-pulse"></div>
            <span className="text-red-400 text-sm font-semibold">LIVE</span>
          </div>
          <div className="font-mono text-2xl font-bold bg-slate-800 px-4 py-2 rounded">01:47.3</div>
        </div>
      </div>

      <div className="grid grid-cols-12 gap-4">
        {/* LEFT COLUMN - Pipeline Progress & Controls */}
        <div className="col-span-8 space-y-4">
          
          {/* Pipeline Progress Bars */}
          <div className="bg-slate-900 rounded-lg p-4 border border-slate-800">
            <div className="flex justify-between items-center mb-4">
              <h2 className="font-semibold text-lg">Pipeline Progress</h2>
              <div className="text-sm text-slate-400">Backlog: <span className="text-orange-400 font-mono font-bold">2.4M txns</span></div>
            </div>
            
            {/* Generated */}
            <div className="mb-6">
              <div className="flex justify-between text-sm mb-1">
                <span className="text-slate-400">Generated</span>
                <span className="font-mono text-white">10,000,000 txns</span>
              </div>
              <div className="h-8 bg-slate-800 rounded-lg overflow-hidden">
                <div className="h-full bg-gradient-to-r from-purple-600 to-purple-400 rounded-lg flex items-center justify-end pr-3" style={{ width: '100%' }}>
                  <span className="text-xs font-mono font-bold">10M</span>
                </div>
              </div>
            </div>

            {/* Data Prep */}
            <div className="mb-6">
              <div className="text-sm text-slate-400 mb-2">Data Prep</div>
              <div className="space-y-2">
                <div>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-blue-400">CPU ({cpuPrepPods} pod{cpuPrepPods > 1 ? 's' : ''})</span>
                    <span className="font-mono">2,100,000</span>
                  </div>
                  <div className="h-6 bg-slate-800 rounded overflow-hidden">
                    <div className="h-full bg-gradient-to-r from-blue-600 to-blue-400 rounded flex items-center justify-end pr-2" style={{ width: '21%' }}>
                      <span className="text-xs font-mono">2.1M</span>
                    </div>
                  </div>
                </div>
                <div>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-emerald-400">GPU ({gpuPrepPods} pod{gpuPrepPods > 1 ? 's' : ''})</span>
                    <span className="font-mono">5,500,000</span>
                  </div>
                  <div className="h-6 bg-slate-800 rounded overflow-hidden">
                    <div className="h-full bg-gradient-to-r from-emerald-600 to-emerald-400 rounded flex items-center justify-end pr-2" style={{ width: '55%' }}>
                      <span className="text-xs font-mono">5.5M</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Inference */}
            <div>
              <div className="text-sm text-slate-400 mb-2">Inference</div>
              <div className="space-y-2">
                <div>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-blue-400">CPU ({cpuInferPods} pod{cpuInferPods > 1 ? 's' : ''})</span>
                    <span className="font-mono">1,800,000</span>
                  </div>
                  <div className="h-6 bg-slate-800 rounded overflow-hidden">
                    <div className="h-full bg-gradient-to-r from-blue-600 to-blue-400 rounded flex items-center justify-end pr-2" style={{ width: '18%' }}>
                      <span className="text-xs font-mono">1.8M</span>
                    </div>
                  </div>
                </div>
                <div>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-emerald-400">GPU ({gpuInferPods} pod{gpuInferPods > 1 ? 's' : ''})</span>
                    <span className="font-mono">4,800,000</span>
                  </div>
                  <div className="h-6 bg-slate-800 rounded overflow-hidden">
                    <div className="h-full bg-gradient-to-r from-emerald-600 to-emerald-400 rounded flex items-center justify-end pr-2" style={{ width: '48%' }}>
                      <span className="text-xs font-mono">4.8M</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Utilization Trend Chart */}
          <div className="bg-slate-900 rounded-lg p-4 border border-slate-800">
            <h2 className="font-semibold mb-4">Utilization Trend</h2>
            <div className="h-40 relative">
              {/* Y-axis labels */}
              <div className="absolute left-0 top-0 bottom-0 w-12 flex flex-col justify-between text-xs text-slate-500 py-1">
                <span>100%</span>
                <span>75%</span>
                <span>50%</span>
                <span>25%</span>
                <span>0%</span>
              </div>
              {/* Chart area */}
              <div className="ml-12 h-full bg-slate-800/50 rounded relative overflow-hidden">
                {/* Grid lines */}
                <div className="absolute inset-0 flex flex-col justify-between py-1">
                  {[0,1,2,3,4].map(i => <div key={i} className="border-t border-slate-700/50"></div>)}
                </div>
                {/* GPU line (high) */}
                <svg className="absolute inset-0 w-full h-full">
                  <polyline
                    fill="none"
                    stroke="#10b981"
                    strokeWidth="2"
                    points="0,60 50,55 100,40 150,35 200,30 250,25 300,20 350,18 400,15 450,15 500,15"
                  />
                  <text x="505" y="18" fill="#10b981" fontSize="10">GPU 85%</text>
                </svg>
                {/* CPU line (medium-high) */}
                <svg className="absolute inset-0 w-full h-full">
                  <polyline
                    fill="none"
                    stroke="#3b82f6"
                    strokeWidth="2"
                    points="0,80 50,70 100,55 150,45 200,40 250,35 300,30 350,28 400,25 450,25 500,22"
                  />
                  <text x="505" y="25" fill="#3b82f6" fontSize="10">CPU 78%</text>
                </svg>
                {/* FlashBlade line (low, flat) */}
                <svg className="absolute inset-0 w-full h-full">
                  <polyline
                    fill="none"
                    stroke="#f97316"
                    strokeWidth="2"
                    strokeDasharray="4,2"
                    points="0,130 50,128 100,125 150,122 200,120 250,118 300,118 350,118 400,118 450,118 500,118"
                  />
                  <text x="505" y="121" fill="#f97316" fontSize="10">FB 12%</text>
                </svg>
              </div>
            </div>
            <div className="flex justify-center gap-6 mt-2 text-xs">
              <span className="flex items-center gap-1"><span className="w-3 h-0.5 bg-emerald-500"></span> GPU</span>
              <span className="flex items-center gap-1"><span className="w-3 h-0.5 bg-blue-500"></span> CPU</span>
              <span className="flex items-center gap-1"><span className="w-3 h-0.5 bg-orange-500"></span> FlashBlade</span>
            </div>
          </div>

          {/* Throughput Trend Chart */}
          <div className="bg-slate-900 rounded-lg p-4 border border-slate-800">
            <h2 className="font-semibold mb-4">Throughput (Txns/sec)</h2>
            <div className="h-40 relative">
              <div className="absolute left-0 top-0 bottom-0 w-12 flex flex-col justify-between text-xs text-slate-500 py-1">
                <span>500K</span>
                <span>375K</span>
                <span>250K</span>
                <span>125K</span>
                <span>0</span>
              </div>
              <div className="ml-12 h-full bg-slate-800/50 rounded relative overflow-hidden">
                <div className="absolute inset-0 flex flex-col justify-between py-1">
                  {[0,1,2,3,4].map(i => <div key={i} className="border-t border-slate-700/50"></div>)}
                </div>
                {/* GPU throughput */}
                <svg className="absolute inset-0 w-full h-full">
                  <polyline
                    fill="none"
                    stroke="#10b981"
                    strokeWidth="2"
                    points="0,130 50,100 100,70 150,50 200,40 250,35 300,30 350,28 400,25 450,25 500,25"
                  />
                  <text x="505" y="28" fill="#10b981" fontSize="10">312K</text>
                </svg>
                {/* CPU throughput */}
                <svg className="absolute inset-0 w-full h-full">
                  <polyline
                    fill="none"
                    stroke="#3b82f6"
                    strokeWidth="2"
                    points="0,135 50,120 100,100 150,90 200,85 250,82 300,80 350,78 400,76 450,76 500,76"
                  />
                  <text x="505" y="79" fill="#3b82f6" fontSize="10">45K</text>
                </svg>
              </div>
            </div>
            <div className="flex justify-center gap-6 mt-2 text-xs">
              <span className="flex items-center gap-1"><span className="w-3 h-0.5 bg-emerald-500"></span> GPU Path</span>
              <span className="flex items-center gap-1"><span className="w-3 h-0.5 bg-blue-500"></span> CPU Path</span>
            </div>
          </div>
        </div>

        {/* RIGHT COLUMN - Business Metrics, Fraud Levels, Controls */}
        <div className="col-span-4 space-y-4">
          
          {/* Business Metrics */}
          <div className="bg-slate-900 rounded-lg p-4 border border-slate-800">
            <h2 className="font-semibold mb-3">Business Impact</h2>
            <div className="grid grid-cols-2 gap-3">
              <div className="bg-slate-800 rounded-lg p-3">
                <div className="text-2xl font-bold font-mono text-emerald-400">$247K</div>
                <div className="text-xs text-slate-400">Fraud Prevented</div>
              </div>
              <div className="bg-slate-800 rounded-lg p-3">
                <div className="text-2xl font-bold font-mono text-white">6.6M</div>
                <div className="text-xs text-slate-400">Txns Scored</div>
              </div>
              <div className="bg-slate-800 rounded-lg p-3">
                <div className="text-2xl font-bold font-mono text-orange-400">4,891</div>
                <div className="text-xs text-slate-400">Fraud Blocked</div>
              </div>
              <div className="bg-slate-800 rounded-lg p-3">
                <div className="text-2xl font-bold font-mono text-purple-400">357K</div>
                <div className="text-xs text-slate-400">Txns/sec</div>
              </div>
            </div>
          </div>

          {/* Fraud Levels - Stacked Bar */}
          <div className="bg-slate-900 rounded-lg p-4 border border-slate-800">
            <h2 className="font-semibold mb-3">Fraud Risk Distribution</h2>
            
            {/* Stacked horizontal bar */}
            <div className="h-10 flex rounded-lg overflow-hidden mb-3">
              <div className="bg-emerald-500 flex items-center justify-center text-xs font-bold" style={{ width: '65%' }}>
                Low (0-60)
              </div>
              <div className="bg-yellow-500 flex items-center justify-center text-xs font-bold text-slate-900" style={{ width: '25%' }}>
                Med (60-90)
              </div>
              <div className="bg-red-500 flex items-center justify-center text-xs font-bold" style={{ width: '10%' }}>
                High
              </div>
            </div>

            {/* Individual bars */}
            <div className="space-y-2">
              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-emerald-400">Low Risk (0-60%)</span>
                  <span className="font-mono">4,290,000</span>
                </div>
                <div className="h-4 bg-slate-800 rounded overflow-hidden">
                  <div className="h-full bg-emerald-500 rounded" style={{ width: '65%' }}></div>
                </div>
              </div>
              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-yellow-400">Medium Risk (60-90%)</span>
                  <span className="font-mono">1,650,000</span>
                </div>
                <div className="h-4 bg-slate-800 rounded overflow-hidden">
                  <div className="h-full bg-yellow-500 rounded" style={{ width: '25%' }}></div>
                </div>
              </div>
              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-red-400">High Risk (90-100%)</span>
                  <span className="font-mono">660,000</span>
                </div>
                <div className="h-4 bg-slate-800 rounded overflow-hidden">
                  <div className="h-full bg-red-500 rounded" style={{ width: '10%' }}></div>
                </div>
              </div>
            </div>
          </div>

          {/* FlashBlade Status */}
          <div className="bg-slate-900 rounded-lg p-4 border border-orange-500/30">
            <div className="flex items-center justify-between mb-3">
              <h2 className="font-semibold">FlashBlade</h2>
              <span className="text-xs text-emerald-400 flex items-center gap-1">
                <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full"></span>
                Connected
              </span>
            </div>
            <div className="grid grid-cols-2 gap-2 mb-3">
              <div className="bg-slate-800 rounded p-2 text-center">
                <div className="text-lg font-bold font-mono text-blue-400">1.2 GB/s</div>
                <div className="text-xs text-slate-400">Read</div>
              </div>
              <div className="bg-slate-800 rounded p-2 text-center">
                <div className="text-lg font-bold font-mono text-emerald-400">850 MB/s</div>
                <div className="text-xs text-slate-400">Write</div>
              </div>
            </div>
            <div className="mb-2">
              <div className="flex justify-between text-xs mb-1">
                <span className="text-slate-400">Utilization</span>
                <span className="text-orange-400 font-mono">12%</span>
              </div>
              <div className="h-3 bg-slate-800 rounded-full overflow-hidden">
                <div className="h-full bg-gradient-to-r from-orange-500 to-orange-400 rounded-full" style={{ width: '12%' }}></div>
              </div>
            </div>
            <div className="text-center text-sm">
              <span className="text-slate-400">Headroom: </span>
              <span className="text-emerald-400 font-bold text-lg">8.3x</span>
            </div>
          </div>

          {/* Scaling Controls */}
          <div className="bg-slate-900 rounded-lg p-4 border border-slate-800">
            <h2 className="font-semibold mb-3">Scaling Controls</h2>
            
            {/* Generator Speed */}
            <div className="mb-4">
              <div className="flex justify-between text-sm mb-2">
                <span className="text-purple-400">Generator Speed</span>
                <span className="font-mono">{generatorSpeed}K txn/s</span>
              </div>
              <input 
                type="range" 
                min="10" 
                max="100" 
                value={generatorSpeed}
                onChange={(e) => setGeneratorSpeed(parseInt(e.target.value))}
                className="w-full h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-purple-500"
              />
            </div>

            {/* Pod Controls */}
            <div className="space-y-3">
              {/* CPU Prep */}
              <div className="flex items-center justify-between">
                <span className="text-sm text-blue-400">CPU Prep Pods</span>
                <div className="flex items-center gap-2">
                  <button 
                    onClick={() => setCpuPrepPods(Math.max(1, cpuPrepPods - 1))}
                    className="w-8 h-8 bg-slate-700 hover:bg-slate-600 rounded flex items-center justify-center font-bold"
                  >-</button>
                  <span className="w-8 text-center font-mono font-bold">{cpuPrepPods}</span>
                  <button 
                    onClick={() => setCpuPrepPods(Math.min(4, cpuPrepPods + 1))}
                    className="w-8 h-8 bg-slate-700 hover:bg-slate-600 rounded flex items-center justify-center font-bold"
                  >+</button>
                </div>
              </div>

              {/* GPU Prep */}
              <div className="flex items-center justify-between">
                <span className="text-sm text-emerald-400">GPU Prep Pods</span>
                <div className="flex items-center gap-2">
                  <button 
                    onClick={() => setGpuPrepPods(Math.max(1, gpuPrepPods - 1))}
                    className="w-8 h-8 bg-slate-700 hover:bg-slate-600 rounded flex items-center justify-center font-bold"
                  >-</button>
                  <span className="w-8 text-center font-mono font-bold">{gpuPrepPods}</span>
                  <button 
                    onClick={() => setGpuPrepPods(Math.min(4, gpuPrepPods + 1))}
                    className="w-8 h-8 bg-slate-700 hover:bg-slate-600 rounded flex items-center justify-center font-bold"
                  >+</button>
                </div>
              </div>

              {/* CPU Infer */}
              <div className="flex items-center justify-between">
                <span className="text-sm text-blue-400">CPU Infer Pods</span>
                <div className="flex items-center gap-2">
                  <button 
                    onClick={() => setCpuInferPods(Math.max(1, cpuInferPods - 1))}
                    className="w-8 h-8 bg-slate-700 hover:bg-slate-600 rounded flex items-center justify-center font-bold"
                  >-</button>
                  <span className="w-8 text-center font-mono font-bold">{cpuInferPods}</span>
                  <button 
                    onClick={() => setCpuInferPods(Math.min(4, cpuInferPods + 1))}
                    className="w-8 h-8 bg-slate-700 hover:bg-slate-600 rounded flex items-center justify-center font-bold"
                  >+</button>
                </div>
              </div>

              {/* GPU Infer */}
              <div className="flex items-center justify-between">
                <span className="text-sm text-emerald-400">GPU Infer Pods</span>
                <div className="flex items-center gap-2">
                  <button 
                    onClick={() => setGpuInferPods(Math.max(1, gpuInferPods - 1))}
                    className="w-8 h-8 bg-slate-700 hover:bg-slate-600 rounded flex items-center justify-center font-bold"
                  >-</button>
                  <span className="w-8 text-center font-mono font-bold">{gpuInferPods}</span>
                  <button 
                    onClick={() => setGpuInferPods(Math.min(4, gpuInferPods + 1))}
                    className="w-8 h-8 bg-slate-700 hover:bg-slate-600 rounded flex items-center justify-center font-bold"
                  >+</button>
                </div>
              </div>
            </div>

            {/* Apply Button */}
            <button className="w-full mt-4 py-2 bg-orange-500 hover:bg-orange-600 rounded-lg font-semibold transition-colors">
              Apply Scaling
            </button>
          </div>

          {/* Start/Stop Controls */}
          <div className="flex gap-2">
            <button className="flex-1 py-3 bg-emerald-600 hover:bg-emerald-700 rounded-lg font-semibold flex items-center justify-center gap-2">
              ▶ Start
            </button>
            <button className="flex-1 py-3 bg-red-600 hover:bg-red-700 rounded-lg font-semibold flex items-center justify-center gap-2">
              ⏹ Stop
            </button>
            <button className="py-3 px-4 bg-slate-700 hover:bg-slate-600 rounded-lg font-semibold">
              ↺
            </button>
          </div>
        </div>
      </div>

      {/* Key Message Bar */}
      <div className="mt-4 bg-gradient-to-r from-orange-500/20 via-orange-500/10 to-transparent rounded-lg p-4 border border-orange-500/30">
        <p className="text-center text-lg">
          💡 Scaled compute <span className="text-emerald-400 font-bold">4x</span> — FlashBlade utilization went from 
          <span className="text-orange-400 font-bold"> 8%</span> to 
          <span className="text-orange-400 font-bold"> 12%</span>. 
          <span className="text-orange-400 font-semibold"> Storage is NOT your bottleneck.</span>
        </p>
      </div>
    </div>
  );
}
