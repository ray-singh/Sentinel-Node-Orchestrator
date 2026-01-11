import React, { useState } from 'react';
import { Database, Server, Activity, AlertCircle, CheckCircle, Clock, DollarSign, Zap, ArrowRight, GitBranch, PlayCircle, PauseCircle, XCircle, Github } from 'lucide-react';

const SentinelDiagram = () => {
  const [activeState, setActiveState] = useState<string | null>(null);

  return (
    <div className="w-full h-full bg-gradient-to-br from-slate-900 to-slate-800 p-8 overflow-auto">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="flex items-center justify-center gap-3 mb-2">
            <h1 className="text-4xl font-bold text-white">
              Sentinel Node Orchestrator
            </h1>
            <a 
              href="https://github.com/ray-singh/Sentinel-Node-Orchestrator" 
              target="_blank" 
              rel="noopener noreferrer"
              className="text-slate-400 hover:text-white transition-colors"
              title="View on GitHub"
            >
              <Github size={32} />
            </a>
          </div>
          <p className="text-slate-300 text-lg">
            Fault-Tolerant Distributed AI Agent System
          </p>
          <div className="flex gap-4 justify-center mt-4 text-sm">
            <div className="flex items-center gap-2 text-green-400">
              <CheckCircle size={16} />
              <span>99.9% Reliability</span>
            </div>
            <div className="flex items-center gap-2 text-blue-400">
              <Zap size={16} />
              <span>130+ tasks/sec</span>
            </div>
            <div className="flex items-center gap-2 text-yellow-400">
              <DollarSign size={16} />
              <span>60% Cost Reduction</span>
            </div>
          </div>
        </div>

        {/* Main Architecture Diagram */}
        <div className="bg-slate-800 rounded-lg p-8 mb-8 shadow-2xl border border-slate-700">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
            {/* Left Column: API & Client */}
            <div className="space-y-6">
              <div className="bg-blue-900/50 border-2 border-blue-500 rounded-lg p-6">
                <div className="flex items-center gap-3 mb-4">
                  <Server className="text-blue-400" size={32} />
                  <div>
                    <h3 className="text-white font-bold text-lg">FastAPI</h3>
                    <p className="text-slate-300 text-sm">REST API</p>
                  </div>
                </div>
                <div className="space-y-2 text-sm text-slate-300">
                  <div className="flex items-start gap-2">
                    <span className="text-blue-400">POST</span>
                    <span>/tasks</span>
                  </div>
                  <div className="flex items-start gap-2">
                    <span className="text-green-400">GET</span>
                    <span>/tasks/:id</span>
                  </div>
                  <div className="flex items-start gap-2">
                    <span className="text-yellow-400">GET</span>
                    <span>/stats</span>
                  </div>
                </div>
              </div>

              <div className="bg-purple-900/50 border-2 border-purple-500 rounded-lg p-6">
                <div className="flex items-center gap-3 mb-4">
                  <Activity className="text-purple-400" size={32} />
                  <div>
                    <h3 className="text-white font-bold text-lg">Watcher</h3>
                    <p className="text-slate-300 text-sm">Health Monitor</p>
                  </div>
                </div>
                <div className="space-y-2 text-sm text-slate-300">
                  <div>✓ Detects dead workers</div>
                  <div>✓ Requeues orphaned tasks</div>
                  <div>✓ Scans every 10s</div>
                </div>
              </div>
            </div>

            {/* Middle Column: Redis */}
            <div className="space-y-6">
              <div className="bg-red-900/50 border-2 border-red-500 rounded-lg p-6">
                <div className="flex items-center gap-3 mb-4">
                  <Database className="text-red-400" size={32} />
                  <div>
                    <h3 className="text-white font-bold text-lg">Redis</h3>
                    <p className="text-slate-300 text-sm">State Store</p>
                  </div>
                </div>
                <div className="space-y-3 text-sm text-slate-300">
                  <div className="bg-slate-700/50 rounded p-2">
                    <div className="font-mono text-xs text-red-300">task:*:meta</div>
                    <div className="text-xs">Task metadata (HASH)</div>
                  </div>
                  <div className="bg-slate-700/50 rounded p-2">
                    <div className="font-mono text-xs text-red-300">task:*:checkpoint</div>
                    <div className="text-xs">Checkpoint state (STRING)</div>
                  </div>
                  <div className="bg-slate-700/50 rounded p-2">
                    <div className="font-mono text-xs text-red-300">worker:*:hb</div>
                    <div className="text-xs">Heartbeats (TTL)</div>
                  </div>
                  <div className="bg-slate-700/50 rounded p-2">
                    <div className="font-mono text-xs text-red-300">ratelimit:*</div>
                    <div className="text-xs">Token buckets (HASH)</div>
                  </div>
                </div>
              </div>

              <div className="bg-orange-900/50 border-2 border-orange-500 rounded-lg p-4">
                <h4 className="text-white font-semibold mb-2 flex items-center gap-2">
                  <Zap size={16} className="text-orange-400" />
                  Lua Scripts
                </h4>
                <div className="text-xs text-slate-300 space-y-1">
                  <div>• Atomic task claiming (SETNX)</div>
                  <div>• Rate limit token consumption</div>
                  <div>• Lease renewal (CAS)</div>
                </div>
              </div>
            </div>

            {/* Right Column: Workers */}
            <div className="space-y-6">
              <div className="bg-green-900/50 border-2 border-green-500 rounded-lg p-6">
                <div className="flex items-center gap-3 mb-4">
                  <Server className="text-green-400" size={32} />
                  <div>
                    <h3 className="text-white font-bold text-lg">Worker Pool</h3>
                    <p className="text-slate-300 text-sm">10+ Workers</p>
                  </div>
                </div>
                <div className="space-y-3">
                  {[1, 2, 3].map((i) => (
                    <div key={i} className="bg-slate-700/50 rounded p-3">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-white font-mono text-sm">worker-{i}</span>
                        <div className="flex items-center gap-1">
                          <div className="w-2 h-2 bg-green-400 rounded-full animate-pulse"></div>
                          <span className="text-xs text-green-400">active</span>
                        </div>
                      </div>
                      <div className="text-xs text-slate-400">
                        • Claim tasks
                      </div>
                      <div className="text-xs text-slate-400">
                        • Execute nodes
                      </div>
                      <div className="text-xs text-slate-400">
                        • Save checkpoints
                      </div>
                      <div className="text-xs text-slate-400">
                        • Send heartbeats
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* Connecting Arrows */}
          <div className="mt-8 text-center text-slate-400 text-sm">
            <div className="flex items-center justify-center gap-4">
              <div className="flex items-center gap-2">
                <div className="w-8 h-0.5 bg-blue-500"></div>
                <span>API Requests</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-8 h-0.5 bg-green-500"></div>
                <span>State Operations</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-8 h-0.5 bg-purple-500"></div>
                <span>Health Checks</span>
              </div>
            </div>
          </div>
        </div>

        {/* Key Features */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <div className="bg-gradient-to-br from-green-900/50 to-green-800/50 border border-green-500 rounded-lg p-6">
            <div className="flex items-center gap-3 mb-3">
              <CheckCircle className="text-green-400" size={32} />
              <h3 className="text-white font-bold text-lg">Fault Tolerance</h3>
            </div>
            <ul className="space-y-2 text-sm text-slate-300">
              <li>• Checkpoint after each node</li>
              <li>• Automatic task resume</li>
              <li>• Lease-based ownership</li>
              <li>• TTL heartbeat monitoring</li>
            </ul>
          </div>

          <div className="bg-gradient-to-br from-blue-900/50 to-blue-800/50 border border-blue-500 rounded-lg p-6">
            <div className="flex items-center gap-3 mb-3">
              <Zap className="text-blue-400" size={32} />
              <h3 className="text-white font-bold text-lg">Performance</h3>
            </div>
            <ul className="space-y-2 text-sm text-slate-300">
              <li>• 130+ tasks/sec throughput</li>
              <li>• Sub-300ms p95 latency</li>
              <li>• Redis pipelining</li>
              <li>• Async worker pools</li>
            </ul>
          </div>

          <div className="bg-gradient-to-br from-yellow-900/50 to-yellow-800/50 border border-yellow-500 rounded-lg p-6">
            <div className="flex items-center gap-3 mb-3">
              <DollarSign className="text-yellow-400" size={32} />
              <h3 className="text-white font-bold text-lg">Cost Control</h3>
            </div>
            <ul className="space-y-2 text-sm text-slate-300">
              <li>• 60% LLM cost reduction</li>
              <li>• Token-bucket rate limiting</li>
              <li>• Per-tenant tracking</li>
              <li>• Intelligent caching</li>
            </ul>
          </div>
        </div>

        {/* Sequence Diagram */}
        <div className="bg-slate-800 rounded-lg p-8 mb-8 shadow-2xl border border-slate-700">
          <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
            <ArrowRight className="text-cyan-400" />
            Sequence Diagram: Task Execution Flow
          </h2>
          
          <div className="space-y-4">
            {/* Actors */}
            <div className="grid grid-cols-5 gap-4 mb-8">
              <div className="text-center">
                <div className="bg-blue-500 rounded-lg p-4 mb-2">
                  <Server size={24} className="mx-auto text-white" />
                </div>
                <div className="text-white font-semibold text-sm">Client</div>
              </div>
              <div className="text-center">
                <div className="bg-green-500 rounded-lg p-4 mb-2">
                  <Server size={24} className="mx-auto text-white" />
                </div>
                <div className="text-white font-semibold text-sm">FastAPI</div>
              </div>
              <div className="text-center">
                <div className="bg-red-500 rounded-lg p-4 mb-2">
                  <Database size={24} className="mx-auto text-white" />
                </div>
                <div className="text-white font-semibold text-sm">Redis</div>
              </div>
              <div className="text-center">
                <div className="bg-purple-500 rounded-lg p-4 mb-2">
                  <Server size={24} className="mx-auto text-white" />
                </div>
                <div className="text-white font-semibold text-sm">Worker</div>
              </div>
              <div className="text-center">
                <div className="bg-orange-500 rounded-lg p-4 mb-2">
                  <Activity size={24} className="mx-auto text-white" />
                </div>
                <div className="text-white font-semibold text-sm">Watcher</div>
              </div>
            </div>

            {/* Sequence Steps */}
            <div className="space-y-3 pl-4">
              <div className="flex items-center gap-3 bg-slate-700/50 p-3 rounded">
                <div className="text-blue-400 font-mono text-sm">1.</div>
                <ArrowRight size={16} className="text-blue-400" />
                <div className="text-slate-300 text-sm">Client → FastAPI: POST /tasks {"{ input, tenant_id }"}</div>
              </div>
              
              <div className="flex items-center gap-3 bg-slate-700/50 p-3 rounded">
                <div className="text-green-400 font-mono text-sm">2.</div>
                <ArrowRight size={16} className="text-green-400" />
                <div className="text-slate-300 text-sm">FastAPI → Redis: HSET task:id:meta + LPUSH task_queue</div>
              </div>
              
              <div className="flex items-center gap-3 bg-slate-700/50 p-3 rounded">
                <div className="text-green-400 font-mono text-sm">3.</div>
                <ArrowRight size={16} className="text-green-400" />
                <div className="text-slate-300 text-sm">FastAPI ← Redis: OK, task_id</div>
              </div>
              
              <div className="flex items-center gap-3 bg-slate-700/50 p-3 rounded">
                <div className="text-blue-400 font-mono text-sm">4.</div>
                <ArrowRight size={16} className="text-blue-400" />
                <div className="text-slate-300 text-sm">Client ← FastAPI: {"{ task_id, status: 'submitted' }"}</div>
              </div>
              
              <div className="flex items-center gap-3 bg-slate-700/50 p-3 rounded">
                <div className="text-purple-400 font-mono text-sm">5.</div>
                <ArrowRight size={16} className="text-purple-400" />
                <div className="text-slate-300 text-sm">Worker → Redis: BRPOP task_queue (blocking)</div>
              </div>
              
              <div className="flex items-center gap-3 bg-slate-700/50 p-3 rounded">
                <div className="text-purple-400 font-mono text-sm">6.</div>
                <ArrowRight size={16} className="text-purple-400" />
                <div className="text-slate-300 text-sm">Worker → Redis: SETNX task:id:lock worker_id (atomic claim)</div>
              </div>
              
              <div className="flex items-center gap-3 bg-slate-700/50 p-3 rounded">
                <div className="text-purple-400 font-mono text-sm">7.</div>
                <ArrowRight size={16} className="text-purple-400" />
                <div className="text-slate-300 text-sm">Worker: Execute LLM node with rate limiting</div>
              </div>
              
              <div className="flex items-center gap-3 bg-slate-700/50 p-3 rounded">
                <div className="text-purple-400 font-mono text-sm">8.</div>
                <ArrowRight size={16} className="text-purple-400" />
                <div className="text-slate-300 text-sm">Worker → Redis: SET task:id:checkpoint state_json</div>
              </div>
              
              <div className="flex items-center gap-3 bg-slate-700/50 p-3 rounded">
                <div className="text-orange-400 font-mono text-sm">9.</div>
                <ArrowRight size={16} className="text-orange-400" />
                <div className="text-slate-300 text-sm">Watcher → Redis: SCAN worker:*:hb (every 10s)</div>
              </div>
              
              <div className="flex items-center gap-3 bg-slate-700/50 p-3 rounded">
                <div className="text-orange-400 font-mono text-sm">10.</div>
                <ArrowRight size={16} className="text-orange-400" />
                <div className="text-slate-300 text-sm">Watcher: Detect expired heartbeats → requeue orphaned tasks</div>
              </div>
            </div>
          </div>
        </div>

        {/* State Machine */}
        <div className="bg-slate-800 rounded-lg p-8 mb-8 shadow-2xl border border-slate-700">
          <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
            <GitBranch className="text-pink-400" />
            State Machine: Task Lifecycle
          </h2>
          
          <div className="flex flex-col items-center space-y-6">
            {/* States */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-6 w-full">
              <div 
                className={`cursor-pointer transition-all ${activeState === 'submitted' ? 'scale-110' : ''}`}
                onMouseEnter={() => setActiveState('submitted')}
                onMouseLeave={() => setActiveState(null)}
              >
                <div className="bg-blue-900/50 border-2 border-blue-500 rounded-lg p-4 text-center">
                  <PlayCircle className="mx-auto mb-2 text-blue-400" size={32} />
                  <div className="text-white font-bold mb-1">SUBMITTED</div>
                  <div className="text-xs text-slate-300">Task created, waiting in queue</div>
                </div>
              </div>

              <div 
                className={`cursor-pointer transition-all ${activeState === 'claimed' ? 'scale-110' : ''}`}
                onMouseEnter={() => setActiveState('claimed')}
                onMouseLeave={() => setActiveState(null)}
              >
                <div className="bg-green-900/50 border-2 border-green-500 rounded-lg p-4 text-center">
                  <CheckCircle className="mx-auto mb-2 text-green-400" size={32} />
                  <div className="text-white font-bold mb-1">CLAIMED</div>
                  <div className="text-xs text-slate-300">Worker acquired lock</div>
                </div>
              </div>

              <div 
                className={`cursor-pointer transition-all ${activeState === 'executing' ? 'scale-110' : ''}`}
                onMouseEnter={() => setActiveState('executing')}
                onMouseLeave={() => setActiveState(null)}
              >
                <div className="bg-purple-900/50 border-2 border-purple-500 rounded-lg p-4 text-center">
                  <Activity className="mx-auto mb-2 text-purple-400" size={32} />
                  <div className="text-white font-bold mb-1">EXECUTING</div>
                  <div className="text-xs text-slate-300">Running LLM nodes</div>
                </div>
              </div>

              <div 
                className={`cursor-pointer transition-all ${activeState === 'checkpoint' ? 'scale-110' : ''}`}
                onMouseEnter={() => setActiveState('checkpoint')}
                onMouseLeave={() => setActiveState(null)}
              >
                <div className="bg-orange-900/50 border-2 border-orange-500 rounded-lg p-4 text-center">
                  <Database className="mx-auto mb-2 text-orange-400" size={32} />
                  <div className="text-white font-bold mb-1">CHECKPOINT</div>
                  <div className="text-xs text-slate-300">State saved to Redis</div>
                </div>
              </div>

              <div 
                className={`cursor-pointer transition-all ${activeState === 'completed' ? 'scale-110' : ''}`}
                onMouseEnter={() => setActiveState('completed')}
                onMouseLeave={() => setActiveState(null)}
              >
                <div className="bg-teal-900/50 border-2 border-teal-500 rounded-lg p-4 text-center">
                  <CheckCircle className="mx-auto mb-2 text-teal-400" size={32} />
                  <div className="text-white font-bold mb-1">COMPLETED</div>
                  <div className="text-xs text-slate-300">Task finished successfully</div>
                </div>
              </div>

              <div 
                className={`cursor-pointer transition-all ${activeState === 'failed' ? 'scale-110' : ''}`}
                onMouseEnter={() => setActiveState('failed')}
                onMouseLeave={() => setActiveState(null)}
              >
                <div className="bg-red-900/50 border-2 border-red-500 rounded-lg p-4 text-center">
                  <XCircle className="mx-auto mb-2 text-red-400" size={32} />
                  <div className="text-white font-bold mb-1">FAILED</div>
                  <div className="text-xs text-slate-300">Max retries exceeded</div>
                </div>
              </div>

              <div 
                className={`cursor-pointer transition-all ${activeState === 'orphaned' ? 'scale-110' : ''}`}
                onMouseEnter={() => setActiveState('orphaned')}
                onMouseLeave={() => setActiveState(null)}
              >
                <div className="bg-yellow-900/50 border-2 border-yellow-500 rounded-lg p-4 text-center">
                  <AlertCircle className="mx-auto mb-2 text-yellow-400" size={32} />
                  <div className="text-white font-bold mb-1">ORPHANED</div>
                  <div className="text-xs text-slate-300">Worker died, requeuing</div>
                </div>
              </div>

              <div 
                className={`cursor-pointer transition-all ${activeState === 'paused' ? 'scale-110' : ''}`}
                onMouseEnter={() => setActiveState('paused')}
                onMouseLeave={() => setActiveState(null)}
              >
                <div className="bg-slate-700/50 border-2 border-slate-500 rounded-lg p-4 text-center">
                  <PauseCircle className="mx-auto mb-2 text-slate-400" size={32} />
                  <div className="text-white font-bold mb-1">PAUSED</div>
                  <div className="text-xs text-slate-300">Rate limit reached</div>
                </div>
              </div>
            </div>

            {/* Transitions */}
            <div className="w-full bg-slate-700/30 rounded-lg p-6">
              <h3 className="text-white font-semibold mb-4">State Transitions</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
                <div className="flex items-center gap-2 text-slate-300">
                  <ArrowRight size={14} className="text-blue-400" />
                  <span>SUBMITTED → CLAIMED (worker claims)</span>
                </div>
                <div className="flex items-center gap-2 text-slate-300">
                  <ArrowRight size={14} className="text-green-400" />
                  <span>CLAIMED → EXECUTING (start node)</span>
                </div>
                <div className="flex items-center gap-2 text-slate-300">
                  <ArrowRight size={14} className="text-purple-400" />
                  <span>EXECUTING → CHECKPOINT (save state)</span>
                </div>
                <div className="flex items-center gap-2 text-slate-300">
                  <ArrowRight size={14} className="text-orange-400" />
                  <span>CHECKPOINT → EXECUTING (next node)</span>
                </div>
                <div className="flex items-center gap-2 text-slate-300">
                  <ArrowRight size={14} className="text-teal-400" />
                  <span>CHECKPOINT → COMPLETED (final node)</span>
                </div>
                <div className="flex items-center gap-2 text-slate-300">
                  <ArrowRight size={14} className="text-red-400" />
                  <span>EXECUTING → FAILED (max retries)</span>
                </div>
                <div className="flex items-center gap-2 text-slate-300">
                  <ArrowRight size={14} className="text-yellow-400" />
                  <span>EXECUTING → ORPHANED (worker crash)</span>
                </div>
                <div className="flex items-center gap-2 text-slate-300">
                  <ArrowRight size={14} className="text-yellow-400" />
                  <span>ORPHANED → SUBMITTED (watcher requeue)</span>
                </div>
                <div className="flex items-center gap-2 text-slate-300">
                  <ArrowRight size={14} className="text-slate-400" />
                  <span>EXECUTING → PAUSED (rate limit)</span>
                </div>
                <div className="flex items-center gap-2 text-slate-300">
                  <ArrowRight size={14} className="text-slate-400" />
                  <span>PAUSED → EXECUTING (tokens available)</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Observability Stack */}
        <div className="bg-slate-800 rounded-lg p-8 shadow-2xl border border-slate-700">
          <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
            <Activity className="text-purple-400" />
            Observability Stack
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="bg-slate-700/50 rounded-lg p-6 border border-purple-500/30">
              <h3 className="text-white font-bold mb-3">OpenTelemetry</h3>
              <div className="space-y-2 text-sm text-slate-300">
                <div>✓ Distributed tracing</div>
                <div>✓ Span attributes</div>
                <div>✓ OTLP export</div>
                <div>✓ Jaeger integration</div>
              </div>
            </div>

            <div className="bg-slate-700/50 rounded-lg p-6 border border-orange-500/30">
              <h3 className="text-white font-bold mb-3">Prometheus</h3>
              <div className="space-y-2 text-sm text-slate-300">
                <div>✓ Custom metrics</div>
                <div>✓ Task counters</div>
                <div>✓ LLM cost tracking</div>
                <div>✓ Latency histograms</div>
              </div>
            </div>

            <div className="bg-slate-700/50 rounded-lg p-6 border border-blue-500/30">
              <h3 className="text-white font-bold mb-3">Grafana</h3>
              <div className="space-y-2 text-sm text-slate-300">
                <div>✓ 15-panel dashboard</div>
                <div>✓ Real-time metrics</div>
                <div>✓ Cost visualization</div>
                <div>✓ Alert configuration</div>
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="mt-8 text-center text-slate-400 text-sm">
          <p>Built with Python, Redis, FastAPI, LangGraph, OpenTelemetry, Prometheus, Grafana</p>
          <p className="mt-2">Hover over state machine states for details</p>
        </div>
      </div>
    </div>
  );
};

export default SentinelDiagram;
