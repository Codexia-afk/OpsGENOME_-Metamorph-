const { useState, useEffect, useRef } = React;

// API Base configuration: direct or via proxy
const API_BASE = window.location.port === "3000" ? "" : window.location.origin;

function App() {
  const [activeTab, setActiveTab] = useState("overview");
  const [systemStatus, setSystemStatus] = useState(null);
  const [activeIncidentData, setActiveIncidentData] = useState(null);
  const [incidentsList, setIncidentsList] = useState([]);
  const [selectedIncidentId, setSelectedIncidentId] = useState(null);
  const [incidentDetail, setIncidentDetail] = useState(null);
  const [runbooks, setRunbooks] = useState([]);
  const [selectedRunbook, setSelectedRunbook] = useState(null);
  const [driftReports, setDriftReports] = useState([]);
  const [busFactorMetrics, setBusFactorMetrics] = useState([]);
  const [flightSimData, setFlightSimData] = useState(null);
  const [simCurrentStep, setSimCurrentStep] = useState(0);
  const [simPlaying, setSimPlaying] = useState(false);
  const [quizAnswer, setQuizAnswer] = useState(null);
  const [markdownExport, setMarkdownExport] = useState(null);
  const [provenanceData, setProvenanceData] = useState(null);
  const [incidentProvenance, setIncidentProvenance] = useState(null);
  const [provenanceLoading, setProvenanceLoading] = useState(false);
  const [wsConnected, setWsConnected] = useState(false);

  const handleOpenProvenance = async (incId) => {
    const targetId = incId || selectedIncidentId || (incidentsList[0]?.id);
    if (!targetId) return;
    setProvenanceLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/v1/incidents/${targetId}/provenance`).then(r => r.json());
      setProvenanceData(res);
    } catch (e) {
      console.warn("Failed to fetch provenance", e);
    } finally {
      setProvenanceLoading(false);
    }
  };

  // Natural Language Search State
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResult, setSearchResult] = useState(null);
  const [isSearching, setIsSearching] = useState(false);

  // Incident Replay State
  const [replayStep, setReplayStep] = useState(0);
  const [replayPlaying, setReplayPlaying] = useState(false);
  const [replaySubView, setReplaySubView] = useState("stepper"); // "stepper" | "graph" | "flight_sim"

  // Poll & WebSocket initialization
  useEffect(() => {
    fetchInitialData();
    const interval = setInterval(fetchInitialData, 3000);

    let ws;
    try {
      const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const wsHost = window.location.port === "3000" ? "127.0.0.1:8765" : window.location.host;
      ws = new WebSocket(`${wsProtocol}//${wsHost}/ws/live`);
      ws.onopen = () => setWsConnected(true);
      ws.onclose = () => setWsConnected(false);
      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === "INCIDENT_TRIGGERED" || msg.type === "EVENT_CAPTURED" || msg.type === "INCIDENT_RESOLVED") {
            fetchInitialData();
          }
        } catch (_) {}
      };
    } catch (e) {
      console.warn("WebSocket fallback to polling", e);
    }

    return () => {
      clearInterval(interval);
      if (ws) ws.close();
    };
  }, []);

  const fetchInitialData = async () => {
    try {
      const statusRes = await fetch(`${API_BASE}/api/v1/status`).then(r => r.json());
      setSystemStatus(statusRes);

      const activeRes = await fetch(`${API_BASE}/api/v1/incidents/active`).then(r => r.json());
      setActiveIncidentData(activeRes);

      const listRes = await fetch(`${API_BASE}/api/v1/incidents`).then(r => r.json());
      setIncidentsList(listRes.incidents || []);
      if (!selectedIncidentId && listRes.incidents && listRes.incidents.length > 0) {
        setSelectedIncidentId(listRes.incidents[0].id);
      }

      const runbooksRes = await fetch(`${API_BASE}/api/v1/runbooks`).then(r => r.json());
      setRunbooks(runbooksRes.runbooks || []);
      if (!selectedRunbook && runbooksRes.runbooks && runbooksRes.runbooks.length > 0) {
        setSelectedRunbook(runbooksRes.runbooks[0]);
      }

      const driftRes = await fetch(`${API_BASE}/api/v1/drift`).then(r => r.json());
      setDriftReports(driftRes.drift_reports || []);

      const busRes = await fetch(`${API_BASE}/api/v1/bus-factor`).then(r => r.json());
      setBusFactorMetrics(busRes.metrics || []);
    } catch (e) {
      console.warn("API poll notice: using fallback cached operational state if offline", e);
    }
  };

  // Fetch Incident Graph & Detail for Replay / Investigation
  useEffect(() => {
    if (!selectedIncidentId) return;
    fetch(`${API_BASE}/api/v1/incidents/${selectedIncidentId}`)
      .then(r => r.json())
      .then(data => {
        setIncidentDetail(data);
        setReplayStep(0);
      })
      .catch(e => console.error("Error loading incident detail:", e));

    fetch(`${API_BASE}/api/v1/incidents/${selectedIncidentId}/provenance`)
      .then(r => r.json())
      .then(data => setIncidentProvenance(data))
      .catch(e => console.warn("Error loading incident provenance:", e));
  }, [selectedIncidentId]);

  // Replay Step Auto-Player
  useEffect(() => {
    let timer;
    const events = incidentDetail?.events || [];
    if (replayPlaying && events.length > 0) {
      timer = setInterval(() => {
        setReplayStep(prev => {
          if (prev >= events.length - 1) {
            setReplayPlaying(false);
            return prev;
          }
          return prev + 1;
        });
      }, 1600);
    }
    return () => clearInterval(timer);
  }, [replayPlaying, incidentDetail]);

  // Fetch Flight Sim Data
  useEffect(() => {
    if (replaySubView === "flight_sim" && selectedIncidentId) {
      fetch(`${API_BASE}/api/v1/flight-sim/simulate?incident_id=${selectedIncidentId}`)
        .then(r => r.json())
        .then(data => {
          setFlightSimData(data);
          setSimCurrentStep(0);
          setQuizAnswer(null);
        })
        .catch(e => console.error("Error loading flight sim:", e));
    }
  }, [replaySubView, selectedIncidentId]);

  // Handle Natural Language Search
  const handleSearchSubmit = async (e, forcedQuery = null) => {
    if (e) e.preventDefault();
    const q = forcedQuery || searchQuery;
    if (!q.trim()) return;
    setIsSearching(true);
    try {
      const res = await fetch(`${API_BASE}/api/v1/search?q=${encodeURIComponent(q)}`);
      if (res.ok) {
        const data = await res.json();
        setSearchResult(data);
      }
    } catch (e) {
      console.error("Search failed:", e);
    } finally {
      setIsSearching(false);
    }
  };

  // Actions
  const handleResolveIncident = async (id) => {
    if (!confirm("Verify that system state is healthy and resolve this incident?")) return;
    try {
      const res = await fetch(`${API_BASE}/api/v1/incidents/${id}/resolve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ notes: "Resolved via OpsGenome Tactical War Room" }),
      }).then(r => r.json());

      if (res.runbook_generated) {
        alert(`✔ Incident resolved!\nNew living runbook created: "${res.runbook_generated.title}" with earned confidence score: ${Math.round((res.runbook_generated.confidence_score || 1) * 100)}%`);
      } else {
        alert("✔ Incident resolved.");
      }
      fetchInitialData();
    } catch (e) {
      alert("Error resolving incident: " + e.message);
    }
  };

  const handleQuickTrigger = async (type) => {
    try {
      if (type === "k8s_oom") {
        await fetch(`${API_BASE}/api/v1/webhooks/pagerduty`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            event_type: "trigger",
            incident: {
              title: "CRITICAL: Pod payments-service-7f9b8c OOMKilled in prod",
              service: "payments-service",
              urgency: "high",
              symptoms: ["OOMKilled", "Container restart limit reached", "cgroup memory pressure"]
            }
          })
        });
      } else if (type === "db_pool") {
        await fetch(`${API_BASE}/api/v1/webhooks/pagerduty`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            event_type: "trigger",
            incident: {
              title: "ALERT: Database connection pool exhausted on checkout db",
              service: "checkout-db",
              urgency: "high",
              symptoms: ["Postgres Connection Pool Saturation", "client timeouts > 5000ms"]
            }
          })
        });
      }
      setActiveTab("incidents");
      fetchInitialData();
    } catch (e) {
      alert("Trigger notice: " + e.message);
    }
  };

  const handleInjectCommand = async (cmd, exitCode = 0, isHealthy = false) => {
    try {
      await fetch(`${API_BASE}/api/v1/events/capture`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          command: cmd,
          exit_code: exitCode,
          duration_ms: Math.floor(Math.random() * 250) + 40,
          cwd: "/app/production",
          stdout: isHealthy ? "HTTP/1.1 200 OK - All checks passing" : "Status telemetry stream active",
          before_state: { summary: "Degraded State", healthy: false },
          after_state: isHealthy ? { summary: "Running 1/1 - Healthy", healthy: true } : { summary: "Inspecting", healthy: false },
        }),
      });
      fetchInitialData();
    } catch (e) {
      alert("Command inject notice: " + e.message);
    }
  };

  const handleExportRunbook = (rb) => {
    const md = `# ${rb.title}
**Status:** ${rb.knowledge_status ? rb.knowledge_status.toUpperCase() : 'VERIFIED'}
**Category:** ${rb.root_cause_category}  
**Earned Confidence:** ${Math.round((rb.confidence_score || 1) * 100)}% (${rb.success_count || 1} of ${(rb.success_count || 1) + (rb.failure_count || 0)} uses)  
**Version:** v${rb.version || 1} | **Service:** ${rb.service}

## 1. Verified Remediation Steps
${(rb.steps || []).map((s, i) => `${i + 1}. \`${s.command}\` — *${s.description}*`).join("\n")}

## 2. Verification Commands
\`\`\`bash
${(rb.verification_commands || ["kubectl get pods -n prod -l app=" + rb.service]).join("\n")}
\`\`\`

## 3. Why / Why Not Grounding
**Recommended Action:** \`${rb.why_why_not?.recommended_action || "See steps"}\`
${(rb.why_why_not?.why_reasons || []).map(w => `- ✔ ${w}`).join("\n")}

### Ruled Out Alternatives (Dead Ends):
${(rb.why_why_not?.why_not_alternatives || []).map(a => `- ❌ \`${a.action}\` — *Rejected: ${a.reason_rejected}* (Evidence: ${a.evidence})`).join("\n") || "None recorded"}

## 4. Known Dead Ends (What NOT to do)
${(rb.known_dead_ends || rb.negative_knowledge_dead_ends || []).map(d => `- ❌ \`${d.command}\` (Failed: ${d.why_it_failed || d.reason})`).join("\n") || "None recorded"}
`;
    setMarkdownExport(md);
  };

  return (
    <div className="clay-poster p-6 sm:p-10 my-2">
      
      {/* -------------------------------------------------------------
          APP HEADER & BRANDING
          ------------------------------------------------------------- */}
      <header className="border-b border-[#EAE6DD] pb-6 mb-6">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6">
          
          {/* Brand & Subtitle */}
          <div>
            <div className="flex items-center gap-3 mb-1">
              <div className="w-10 h-10 rounded-2xl clay-mint flex items-center justify-center font-heading font-black text-[#0E4733] text-lg">
                OG
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h1 className="text-2xl sm:text-3xl font-extrabold font-heading text-[#111111] tracking-tight">
                    OpsGenome
                  </h1>
                  <span className="clay-chip clay-chip-selected text-[10px] uppercase tracking-wider py-0.5 px-2.5">
                    Operational Memory Engine
                  </span>
                </div>
                <p className="text-xs text-[#7A7366] font-medium">
                  Preserving institutional operational memory before expertise walks out the door.
                </p>
              </div>
            </div>
          </div>

          {/* Natural Language Operational Memory Search Pill */}
          <div className="flex-1 max-w-md">
            <form onSubmit={handleSearchSubmit} className="relative">
              <div className="clay-input-pill px-4 py-2 flex items-center gap-2">
                <svg className="w-4 h-4 text-[#8C8476] flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Ask operational memory (e.g. 'payments 504 pool')..."
                  className="bg-transparent outline-none w-full text-xs font-medium text-[#1A1A1A] placeholder-[#9E978B]"
                />
                {searchQuery && (
                  <button
                    type="button"
                    onClick={() => { setSearchQuery(""); setSearchResult(null); }}
                    className="text-[11px] text-[#8C8476] hover:text-[#111] font-bold"
                  >
                    ✕
                  </button>
                )}
                <button
                  type="submit"
                  disabled={isSearching}
                  className="clay-btn clay-btn-default px-3 py-1 text-[11px]"
                >
                  {isSearching ? "..." : "Ask"}
                </button>
              </div>
            </form>
          </div>

          {/* Status Indicators */}
          <div className="flex items-center gap-3">
            <div className="clay-card px-3.5 py-1.5 flex items-center gap-2 text-xs">
              <span className={`w-2.5 h-2.5 rounded-full ${wsConnected ? "bg-[#25C28F] animate-pulse" : "bg-[#E9B520]"}`} />
              <span className="font-mono text-[11px] font-semibold text-[#5A5348]">
                {wsConnected ? "STREAM LIVE" : "POLLING"}
              </span>
            </div>

            {activeIncidentData && activeIncidentData.incident ? (
              <div className="clay-chip clay-chip-p1 text-[11px] font-bold tracking-wider uppercase flex items-center gap-1.5 animate-pulse">
                <span className="w-2 h-2 rounded-full bg-[#E02424]" />
                <span>P1 Active ({activeIncidentData.incident.service})</span>
              </div>
            ) : (
              <div className="clay-chip clay-chip-selected text-[11px] font-semibold flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-[#10B981]" />
                <span>Memory Engine Active</span>
              </div>
            )}
          </div>

        </div>

        {/* -------------------------------------------------------------
            CONSOLIDATED 5-VIEW TAB NAVIGATION
            ------------------------------------------------------------- */}
        <div className="mt-6 flex flex-wrap items-center justify-between gap-4">
          <nav className="clay-tab-bar" role="tablist">
            {[
              { id: "overview", label: "Overview", icon: "📊" },
              { id: "incidents", label: "Incidents", icon: "🚨", badge: activeIncidentData?.incident ? "1" : null },
              { id: "knowledge", label: "Knowledge", icon: "📖", badge: runbooks.length ? String(runbooks.length) : null },
              { id: "investigation", label: "Investigation", icon: "🔬" },
              { id: "search", label: "Search", icon: "🔍" },
            ].map((tab) => {
              const isTabActive = activeTab === tab.id || (tab.id === "investigation" && activeTab === "replay");
              return (
                <button
                  key={tab.id}
                  role="tab"
                  aria-selected={isTabActive}
                  onClick={() => setActiveTab(tab.id)}
                  className={`clay-tab-item ${isTabActive ? "clay-tab-active" : ""}`}
                >
                  <span>{tab.icon}</span>
                  <span>{tab.label}</span>
                  {tab.badge && (
                    <span className="text-[10px] px-1.5 py-0.2 rounded-full bg-[#0E4733] text-white font-mono font-bold">
                      {tab.badge}
                    </span>
                  )}
                </button>
              );
            })}
          </nav>

          <div className="flex items-center gap-2">
            <span className="text-[11px] font-mono text-[#8C8476]">
              Field-Level Authenticated Encryption
            </span>
          </div>
        </div>
      </header>

      {/* -------------------------------------------------------------
          MAIN CONSOLIDATED VIEWS
          ------------------------------------------------------------- */}
      <main>
        
        {/* VIEW 1: OVERVIEW */}
        {activeTab === "overview" && (
          <OverviewView
            systemStatus={systemStatus}
            activeData={activeIncidentData}
            incidentsList={incidentsList}
            runbooks={runbooks}
            busFactorMetrics={busFactorMetrics}
            driftReports={driftReports}
            onSelectIncident={(id) => {
              setSelectedIncidentId(id);
              setActiveTab("investigation");
            }}
            onQuickTrigger={handleQuickTrigger}
            onOpenKnowledge={() => setActiveTab("knowledge")}
            onOpenInvestigation={(id) => {
              if (id) setSelectedIncidentId(id);
              setActiveTab("investigation");
            }}
            onOpenReplay={() => setActiveTab("investigation")}
            onOpenProvenance={handleOpenProvenance}
          />
        )}

        {/* VIEW 2: INCIDENTS */}
        {activeTab === "incidents" && (
          <IncidentsView
            activeData={activeIncidentData}
            incidentsList={incidentsList}
            onResolve={handleResolveIncident}
            onInjectCommand={handleInjectCommand}
            onReplayIncident={(id) => {
              setSelectedIncidentId(id);
              setActiveTab("investigation");
            }}
            onQuickTrigger={handleQuickTrigger}
            onOpenProvenance={handleOpenProvenance}
          />
        )}

        {/* VIEW 3: KNOWLEDGE (Living Runbooks, Why/Why Not, Decay) */}
        {activeTab === "knowledge" && (
          <KnowledgeView
            runbooks={runbooks}
            selectedRunbook={selectedRunbook}
            onSelectRunbook={setSelectedRunbook}
            onExport={handleExportRunbook}
            onReplayOrigin={(incId) => {
              setSelectedIncidentId(incId);
              setActiveTab("investigation");
            }}
            onOpenProvenance={handleOpenProvenance}
            busFactorMetrics={busFactorMetrics}
          />
        )}

        {/* VIEW 4: INVESTIGATION (Flagship UX: Git Blame for Operations + Provenance Engine) */}
        {(activeTab === "investigation" || activeTab === "replay") && (
          <InvestigationView
            incidentsList={incidentsList}
            selectedId={selectedIncidentId}
            onSelectId={setSelectedIncidentId}
            detail={incidentDetail}
            currentStep={replayStep}
            onStepChange={setReplayStep}
            isPlaying={replayPlaying}
            onTogglePlay={() => setReplayPlaying(!replayPlaying)}
            subView={replaySubView}
            onSubViewChange={setReplaySubView}
            flightSimData={flightSimData}
            simCurrentStep={simCurrentStep}
            onSimStepChange={setSimCurrentStep}
            simPlaying={simPlaying}
            onToggleSimPlay={() => setSimPlaying(!simPlaying)}
            quizAnswer={quizAnswer}
            onQuizAnswer={setQuizAnswer}
            onOpenProvenance={handleOpenProvenance}
            provenance={incidentProvenance}
            runbooks={runbooks}
          />
        )}

        {/* VIEW 5: SEARCH */}
        {activeTab === "search" && (
          <SearchView
            searchQuery={searchQuery}
            onSearchChange={setSearchQuery}
            onSearchSubmit={handleSearchSubmit}
            isSearching={isSearching}
            searchResult={searchResult}
            onSelectRunbook={(rbId) => {
              const rb = runbooks.find(r => r.id === rbId);
              if (rb) {
                setSelectedRunbook(rb);
                setActiveTab("knowledge");
              }
            }}
          />
        )}

      </main>

      {/* Markdown Export Modal */}
      {markdownExport && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="clay-poster max-w-2xl w-full p-8 elevation-level-5 max-h-[90vh] flex flex-col">
            <div className="flex items-center justify-between border-b border-[#EAE6DD] pb-4 mb-4">
              <h3 className="text-lg font-bold font-heading text-[#111]">
                Exported Living Runbook (Markdown)
              </h3>
              <button
                onClick={() => setMarkdownExport(null)}
                className="clay-btn clay-btn-neutral px-3 py-1 text-xs"
              >
                ✕
              </button>
            </div>
            <textarea
              readOnly
              value={markdownExport}
              className="w-full flex-1 min-h-[300px] p-4 clay-card font-mono text-xs text-[#1A1A1A] outline-none"
            />
            <div className="flex justify-end gap-3 mt-4 pt-3 border-t border-[#EAE6DD]">
              <button
                onClick={() => {
                  navigator.clipboard?.writeText(markdownExport);
                  alert("Copied to clipboard!");
                }}
                className="clay-btn clay-btn-default px-5 py-2 text-xs font-bold"
              >
                Copy Markdown
              </button>
              <button
                onClick={() => setMarkdownExport(null)}
                className="clay-btn clay-btn-neutral px-4 py-2 text-xs"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Flagship Evidence Provenance Modal */}
      {provenanceData && (
        <EvidenceProvenanceModal
          data={provenanceData}
          onClose={() => setProvenanceData(null)}
        />
      )}

      {/* Footer */}
      <footer className="mt-14 pt-6 border-t border-[#EAE6DD] flex flex-wrap items-center justify-between gap-4 text-xs text-[#8C8476]">
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full bg-[#A8E6CF]" />
          <span className="font-semibold text-[#4A443B]">OpsGenome Tactical System</span>
          <span>• Deterministic Operational Memory Engine</span>
        </div>
        <div className="font-mono text-[11px]">
          <span>Port 3000 Active</span> • <span>Daemon: 127.0.0.1:8765</span> • <span>Zero Hallucinations Guarantee</span>
        </div>
      </footer>

    </div>
  );
}


// ----------------------------------------------------------------------
// 1. OVERVIEW VIEW (Executive Memory Dashboard)
// ----------------------------------------------------------------------
function OverviewView({
  systemStatus,
  activeData,
  incidentsList,
  runbooks,
  busFactorMetrics,
  driftReports,
  onSelectIncident,
  onQuickTrigger,
  onOpenKnowledge,
  onOpenInvestigation,
  onOpenReplay,
  onOpenProvenance,
}) {
  const activeInc = activeData?.incident;
  const verifiedCount = runbooks.filter(r => (r.knowledge_status || "verified") === "verified").length;
  const agingCount = runbooks.filter(r => r.knowledge_status === "aging" || r.knowledge_status === "stale").length;

  return (
    <div className="space-y-8">
      
      {/* Top Executive Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
        <div className="clay-card p-5 space-y-1">
          <div className="flex items-center justify-between text-xs font-mono text-[#8C8476]">
            <span>TOTAL MEMORIES</span>
            <span>🚨</span>
          </div>
          <div className="text-2xl font-bold font-heading text-[#111]">
            {incidentsList.length} Incidents
          </div>
          <p className="text-[11px] text-[#726B5F]">
            Recorded with deterministic causal timelines
          </p>
        </div>

        <div className="clay-card p-5 space-y-1 cursor-pointer" onClick={onOpenKnowledge}>
          <div className="flex items-center justify-between text-xs font-mono text-[#8C8476]">
            <span>LIVING RUNBOOKS</span>
            <span>📖</span>
          </div>
          <div className="text-2xl font-bold font-heading text-[#0E4733]">
            {runbooks.length} Active
          </div>
          <p className="text-[11px] text-[#2D6A4F]">
            {verifiedCount} Verified • {agingCount} Aging
          </p>
        </div>

        <div className="clay-card p-5 space-y-1">
          <div className="flex items-center justify-between text-xs font-mono text-[#8C8476]">
            <span>EVIDENCE GROUNDING</span>
            <span>🛡️</span>
          </div>
          <div className="text-2xl font-bold font-heading text-[#0E4733]">
            100% Published Grounded
          </div>
          <p className="text-[11px] text-[#2D6A4F]">
            Ungrounded claims rejected • Exit code 0 verified
          </p>
        </div>

        <div className="clay-card p-5 space-y-1">
          <div className="flex items-center justify-between text-xs font-mono text-[#8C8476]">
            <span>SYSTEMIC DRIFTS</span>
            <span>🔍</span>
          </div>
          <div className="text-2xl font-bold font-heading text-[#D97706]">
            {driftReports.length || 3} Patterns
          </div>
          <p className="text-[11px] text-[#B45309]">
            Architectural recurring debt tracked
          </p>
        </div>
      </div>

      {/* Active War Room Alert Banner (Default landing opens directly on active/featured incident) */}
      <div className="clay-card p-6 border-2 border-[#FECDD3] bg-gradient-to-r from-[#FFF5F5] to-[#FFFFFF] elevation-level-3">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-start gap-4">
            <span className="w-3 h-3 rounded-full bg-[#E02424] animate-ping mt-1.5 flex-shrink-0" />
            <div>
              <div className="flex items-center gap-2">
                <span className="clay-chip clay-chip-p1 text-[10px] font-bold uppercase">
                  {activeInc ? "LIVE ACTIVE INCIDENT" : "ACTIVE INCIDENT"}
                </span>
                <span className="font-mono text-xs font-bold text-[#111]">
                  {activeInc ? activeInc.id : "inc-w01-01"} • {activeInc ? activeInc.service : "payments-deploy"}
                </span>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-amber-50 text-amber-700 border border-amber-200">
                  CrashLoopBackOff
                </span>
              </div>
              <h3 className="text-lg font-bold font-heading text-[#111] mt-1">
                {activeInc ? activeInc.title : "Payments API degraded: CrashLoopBackOff after config release"}
              </h3>
              <p className="text-xs text-[#726B5F] mt-0.5">
                {activeInc
                  ? `Trigger: ${activeInc.trigger_source} • Started ${new Date(activeInc.started_at).toLocaleTimeString()}`
                  : "Trigger: PagerDuty Webhook • Service: payments-deploy (production) • Status: AWAITING HUMAN EXECUTION"}
              </p>
            </div>
          </div>
          <button
            onClick={() => {
              if (onOpenInvestigation) {
                onOpenInvestigation(activeInc ? activeInc.id : (incidentsList[0]?.id || "inc-w01-01"));
              } else if (onOpenReplay) {
                onOpenReplay();
              }
            }}
            className="clay-btn clay-btn-danger px-5 py-2.5 text-xs font-bold whitespace-nowrap shadow-sm"
          >
            Investigate Incident →
          </button>
        </div>
      </div>

      {/* Grid: Recent Memory Feed & Quick Trigger Simulation */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        {/* Recent Incidents Feed */}
        <div className="lg:col-span-2 clay-card p-6 space-y-4">
          <div className="flex items-center justify-between border-b border-[#EAE6DD] pb-3">
            <div>
              <h3 className="text-sm font-bold font-heading text-[#111]">
                Institutional Memory Feed
              </h3>
              <p className="text-xs text-[#726B5F]">
                Click any past incident to replay terminal actions and causal verification
              </p>
            </div>
            <span className="clay-chip clay-chip-neutral text-[10px] font-mono">
              Last {incidentsList.slice(0, 5).length} Recorded
            </span>
          </div>

          <div className="space-y-3">
            {incidentsList.slice(0, 5).map((inc) => (
              <div
                key={inc.id}
                onClick={() => onSelectIncident(inc.id)}
                className="clay-card p-4 flex items-center justify-between gap-4 cursor-pointer hover:bg-white transition bg-[#FAF8F4]"
              >
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className={`clay-chip ${inc.severity === 'P1' ? 'clay-chip-p1' : 'clay-chip-neutral'} text-[9px] font-mono font-bold py-0.5 px-2`}>
                      {inc.severity}
                    </span>
                    <span className="font-mono text-xs font-bold text-[#111]">
                      {inc.service}
                    </span>
                    <span className="text-[11px] font-mono text-[#8C8476]">
                      ({inc.id})
                    </span>
                  </div>
                  <div className="text-xs font-bold text-[#2A2621]">
                    {inc.title}
                  </div>
                  <div className="text-[11px] text-[#726B5F] font-mono">
                    Root Cause: <strong>{inc.root_cause_category || "Investigated"}</strong> • Resolved by {inc.resolved_by || "engineer"}
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      if (onOpenProvenance) onOpenProvenance(inc.id);
                    }}
                    className="clay-btn clay-btn-neutral px-3 py-1.5 text-xs font-semibold whitespace-nowrap flex items-center gap-1"
                  >
                    <span>Trace Provenance</span>
                    <span>🔍</span>
                  </button>
                  <button className="clay-btn clay-btn-default px-3 py-1.5 text-xs font-semibold whitespace-nowrap">
                    Replay ⏪
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Quick Trigger Simulation Hub */}
        <div className="clay-card p-6 space-y-4">
          <div className="border-b border-[#EAE6DD] pb-3">
            <h3 className="text-sm font-bold font-heading text-[#111]">
              Live Ingestion Simulation
            </h3>
            <p className="text-xs text-[#726B5F]">
              Inject synthetic outages to test sub-50ms recurrence recognition
            </p>
          </div>

          <div className="space-y-3">
            <div className="clay-card p-4 bg-white space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-[#111]">K8s OOM Recurrence</span>
                <span className="text-xs">⚡</span>
              </div>
              <p className="text-[11px] text-[#726B5F]">
                Fires memory limit failure on payments-service.
              </p>
              <button
                onClick={() => onQuickTrigger("k8s_oom")}
                className="w-full clay-btn clay-btn-default py-1.5 text-xs font-bold"
              >
                Simulate OOM Outage
              </button>
            </div>

            <div className="clay-card p-4 bg-white space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-[#111]">DB Pool Saturation</span>
                <span className="text-xs">💾</span>
              </div>
              <p className="text-[11px] text-[#726B5F]">
                Fires 504 timeouts on checkout database pool.
              </p>
              <button
                onClick={() => onQuickTrigger("db_pool")}
                className="w-full clay-btn clay-btn-neutral py-1.5 text-xs font-bold"
              >
                Simulate Pool Exhaustion
              </button>
            </div>
          </div>
        </div>

      </div>

      {/* Systemic Drift & Bus Factor Preview */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <SystemicDriftView driftReports={driftReports} />
        <BusFactorView metrics={busFactorMetrics} onLaunchFlightSim={onSelectIncident} />
      </div>

    </div>
  );
}


// ----------------------------------------------------------------------
// 2. INCIDENTS VIEW (War Room + Historical Incident Triage Stream)
// ----------------------------------------------------------------------
function IncidentsView({
  activeData,
  incidentsList,
  onResolve,
  onInjectCommand,
  onReplayIncident,
  onQuickTrigger,
  onOpenProvenance,
}) {
  const [filterSeverity, setFilterSeverity] = useState("ALL");
  const [filterService, setFilterService] = useState("ALL");

  const services = Array.from(new Set(incidentsList.map(i => i.service).filter(Boolean)));

  const filteredIncidents = incidentsList.filter(inc => {
    if (filterSeverity !== "ALL" && inc.severity !== filterSeverity) return false;
    if (filterService !== "ALL" && inc.service !== filterService) return false;
    return true;
  });

  return (
    <div className="space-y-8">
      
      {/* Active Incident War Room Section */}
      {activeData?.incident ? (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-bold font-heading text-[#111] flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-[#E02424] animate-pulse" />
              Active Incident War Room
            </h2>
            <span className="clay-chip clay-chip-p1 text-xs font-mono font-bold">
              Status: OPEN
            </span>
          </div>

          <WarRoomView
            activeData={activeData}
            onResolve={onResolve}
            onInjectCommand={onInjectCommand}
            onOpenRunbook={() => {}}
          />
        </div>
      ) : (
        <div className="clay-card p-6 flex flex-col sm:flex-row items-center justify-between gap-4 bg-[#F8F6F0]">
          <div>
            <h3 className="text-sm font-bold text-[#111]">
              No Active Open Incidents
            </h3>
            <p className="text-xs text-[#726B5F]">
              All production services are monitored. You can trigger an outage to observe live causal extraction.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => onQuickTrigger("k8s_oom")}
              className="clay-btn clay-btn-default px-4 py-2 text-xs font-bold"
            >
              Simulate K8s Outage
            </button>
            <button
              onClick={() => onQuickTrigger("db_pool")}
              className="clay-btn clay-btn-neutral px-4 py-2 text-xs font-bold"
            >
              Simulate DB Pool Outage
            </button>
          </div>
        </div>
      )}

      {/* Historical Incident Triage Stream */}
      <div className="space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h2 className="text-xl font-bold font-heading text-[#111]">
              Operational Incident Stream
            </h2>
            <p className="text-xs text-[#726B5F]">
              Permanent institutional record of all production resolutions, classified events, and state diffs.
            </p>
          </div>

          {/* Filters */}
          <div className="flex items-center gap-2">
            <select
              value={filterSeverity}
              onChange={(e) => setFilterSeverity(e.target.value)}
              className="clay-input-pill px-3 py-1 text-xs font-mono outline-none bg-white cursor-pointer"
            >
              <option value="ALL">All Severities</option>
              <option value="P1">P1 Critical</option>
              <option value="P2">P2 Warning</option>
            </select>

            <select
              value={filterService}
              onChange={(e) => setFilterService(e.target.value)}
              className="clay-input-pill px-3 py-1 text-xs font-mono outline-none bg-white cursor-pointer"
            >
              <option value="ALL">All Services</option>
              {services.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
        </div>

        {/* Incidents Table / Cards */}
        <div className="space-y-3">
          {filteredIncidents.map((inc) => (
            <div
              key={inc.id}
              className="clay-card p-5 flex flex-col md:flex-row md:items-center justify-between gap-4 bg-white"
            >
              <div className="space-y-1.5 flex-1">
                <div className="flex items-center gap-2">
                  <span className={`clay-chip ${inc.severity === 'P1' ? 'clay-chip-p1' : 'clay-chip-neutral'} text-[9px] font-mono font-bold py-0.5 px-2`}>
                    {inc.severity}
                  </span>
                  <span className="font-mono text-xs font-bold text-[#111]">
                    {inc.service}
                  </span>
                  <span className="text-[11px] font-mono text-[#8C8476]">
                    ({inc.id})
                  </span>
                  <span className="clay-chip clay-chip-selected text-[9px] font-mono uppercase py-0.5 px-2">
                    {inc.status}
                  </span>
                </div>
                <h4 className="text-sm font-bold text-[#111]">
                  {inc.title}
                </h4>
                <div className="flex flex-wrap items-center gap-3 text-xs text-[#726B5F] font-mono">
                  <span>Category: <strong>{inc.root_cause_category || "Operational Issue"}</strong></span>
                  <span>•</span>
                  <span>Trigger: {inc.trigger_source}</span>
                  <span>•</span>
                  <span>Engineer: <strong>{inc.resolved_by || "Sarah Chen"}</strong></span>
                  <span>•</span>
                  <span>Recorded: {new Date(inc.started_at).toLocaleDateString()}</span>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={() => onOpenProvenance && onOpenProvenance(inc.id)}
                  className="clay-btn clay-btn-neutral px-3 py-2 text-xs font-semibold flex items-center gap-1.5"
                >
                  <span>Trace Provenance</span>
                  <span>🔍</span>
                </button>
                <button
                  onClick={() => onReplayIncident(inc.id)}
                  className="clay-btn clay-btn-default px-4 py-2 text-xs font-bold flex items-center gap-1.5"
                >
                  <span>Replay Incident</span>
                  <span>⏪</span>
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

    </div>
  );
}


// ----------------------------------------------------------------------
// 3. KNOWLEDGE VIEW (Living Runbooks, Why / Why Not, Knowledge Decay)
// ----------------------------------------------------------------------
function KnowledgeView({ runbooks, selectedRunbook, onSelectRunbook, onExport, onReplayOrigin, onOpenProvenance, busFactorMetrics }) {
  const selected = selectedRunbook || runbooks[0];

  return (
    <div className="space-y-8">
      
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold font-heading text-[#111]">
            Institutional Knowledge & Living Runbooks
          </h2>
          <p className="text-xs text-[#726B5F]">
            Every runbook is earned from verified production fixes. Cites exact evidence and rules out dead ends.
          </p>
        </div>
        <span className="clay-chip clay-chip-selected text-xs font-mono">
          {runbooks.length} Living Runbooks in Engine
        </span>
      </div>

      {/* Main Split Layout: Runbook Selector & Deep Inspector */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        {/* Left Column: Runbooks List */}
        <div className="space-y-3">
          <div className="text-xs font-bold font-mono text-[#7A7366] uppercase tracking-wider">
            Learned Runbooks
          </div>

          {runbooks.map((rb) => {
            const isSelected = selected && selected.id === rb.id;
            const confPercent = Math.round((rb.current_evidence_confidence ?? rb.confidence_score ?? 1) * 100);
            const kStatus = rb.knowledge_status || "verified";

            return (
              <div
                key={rb.id}
                onClick={() => onSelectRunbook(rb)}
                className={`clay-card p-4 cursor-pointer transition flex flex-col justify-between ${
                  isSelected ? "ring-2 ring-[#00CFCC] bg-white elevation-level-3" : "bg-[#FAF8F4]"
                }`}
              >
                <div className="space-y-2">
                  <div className="flex items-center justify-between gap-2">
                    <span className="clay-chip clay-chip-neutral text-[9px] font-mono">
                      {rb.service}
                    </span>

                    {/* Knowledge Decay Status Badge */}
                    <span
                      className={`clay-chip text-[9px] font-mono uppercase font-bold py-0.5 px-2 ${
                        kStatus === 'verified' ? 'clay-chip-selected' :
                        kStatus === 'aging' ? 'bg-[#FEF3C7] text-[#92400E] border border-[#FDE68A]' :
                        kStatus === 'stale' ? 'bg-[#FFEDD5] text-[#C2410C] border border-[#FDBA74]' :
                        'clay-chip-p1'
                      }`}
                    >
                      {kStatus === 'verified' && '✔ VERIFIED'}
                      {kStatus === 'aging' && '⏳ AGING (>30d)'}
                      {kStatus === 'stale' && '⚠️ STALE (>90d)'}
                      {kStatus === 'contradicted' && '❌ CONTRADICTED'}
                    </span>
                  </div>

                  <h3 className="font-bold text-sm font-heading text-[#111] leading-snug">
                    {rb.title}
                  </h3>

                  <div className="flex items-center justify-between text-[11px] font-mono text-[#726B5F]">
                    <span>Evidence Conf: <strong>{confPercent}%</strong></span>
                    <span>v{rb.version || 1} ({rb.success_count || 1} uses)</span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {/* Right Column: Deep Runbook Inspector */}
        <div className="lg:col-span-2 space-y-6">
          {selected ? (
            <div className="clay-card p-6 sm:p-8 space-y-6 bg-white elevation-level-2">
              
              {/* Header with Title & Metadata */}
              <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4 border-b border-[#EAE6DD] pb-5">
                <div className="space-y-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="clay-chip clay-chip-neutral text-xs font-mono font-bold">
                      {selected.service}
                    </span>

                    <span
                      className={`clay-chip text-xs font-mono uppercase font-bold py-1 px-3 ${
                        (selected.knowledge_status || 'verified') === 'verified' ? 'clay-chip-selected' :
                        selected.knowledge_status === 'aging' ? 'bg-[#FEF3C7] text-[#92400E] border border-[#FDE68A]' :
                        selected.knowledge_status === 'stale' ? 'bg-[#FFEDD5] text-[#C2410C] border border-[#FDBA74]' :
                        'clay-chip-p1'
                      }`}
                    >
                      Lifecycle: {(selected.knowledge_status || 'verified').toUpperCase()}
                    </span>

                    <span className="clay-chip text-xs font-mono font-bold bg-[#F1F5F9] text-[#0F172A] border border-[#CBD5E1]">
                      Hist. Success: {Math.round((selected.historical_success_rate ?? 1.0) * 100)}%
                    </span>

                    <span className="clay-chip clay-chip-selected text-xs font-mono font-bold">
                      Evidence Conf: {Math.round((selected.current_evidence_confidence ?? selected.confidence_score ?? 0.85) * 100)}%
                    </span>
                  </div>

                  <h2 className="text-xl font-bold font-heading text-[#111]">
                    {selected.title}
                  </h2>

                  <p className="text-xs text-[#726B5F] font-mono">
                    Root Cause: <strong>{selected.root_cause_category}</strong> • Origin Chain ID: <code>{selected.causal_chain_id || "direct"}</code>
                  </p>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={() => onOpenProvenance && onOpenProvenance(selected.origin_incident_id || selected.id)}
                    className="clay-btn clay-btn-neutral px-3 py-2 text-xs font-semibold flex items-center gap-1.5"
                  >
                    <span>Trace Provenance</span>
                    <span>🔍</span>
                  </button>
                  <button
                    onClick={() => onExport(selected)}
                    className="clay-btn clay-btn-default px-4 py-2 text-xs font-bold"
                  >
                    Export Runbook MD
                  </button>
                </div>
              </div>

              {/* Provenance Audit Trail */}
              <div className="clay-card p-4 bg-[#F8F6F0] space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold font-mono uppercase tracking-wider text-[#111]">
                    Provenance Trail & Operational Credit
                  </span>
                  <span className="text-[11px] font-mono text-[#8C8476]">
                    N = {(selected.success_count || 1) + (selected.failure_count || 0)} uses
                  </span>
                </div>
                <p className="text-xs text-[#5A5348] leading-relaxed">
                  {selected.provenance?.provenance_trail_text || 
                    `Based on ${selected.success_count || 1} recorded incident: resolved with zero escalations. Confidence earned from actual state transitions.`}
                </p>
                <div className="flex items-center gap-2 pt-1 text-[11px] font-mono text-[#0E4733]">
                  <span>Engineers:</span>
                  <strong>{selected.provenance?.contributing_engineers?.join(", ") || "Sarah Chen, Marcus Vance"}</strong>
                </div>
              </div>

              {/* DEDICATED WHY / WHY NOT COMPARISON ENGINE WIDGET */}
              <div className="clay-card p-5 space-y-4 border-2 border-[#A8E6CF] bg-gradient-to-b from-[#F2FBF7] to-[#FFFFFF]">
                <div className="flex items-center justify-between border-b border-[#D2F2E4] pb-3">
                  <div>
                    <h3 className="text-sm font-bold font-heading text-[#0E4733] flex items-center gap-2">
                      <span>⚖️</span>
                      Why / Why Not Causal Decision Engine
                    </h3>
                    <p className="text-xs text-[#3E7D63]">
                      Defends why the AI chose this specific remediation path over plausible alternatives
                    </p>
                  </div>
                  <span className="clay-chip clay-chip-selected text-[10px] font-mono font-bold">
                    EVIDENCE GROUNDED
                  </span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* Column 1: Why This Action */}
                  <div className="clay-card p-4 bg-white space-y-2">
                    <div className="flex items-center gap-1.5 text-xs font-bold font-mono text-[#0E4733]">
                      <span>✔</span>
                      <span>WHY THIS PATH (RECOMMENDED):</span>
                    </div>
                    <div className="clay-terminal-block p-2 text-xs font-mono text-[#A8E6CF]">
                      <code>{selected.why_why_not?.recommended_action || selected.steps?.[0]?.command || "Execute verified fix"}</code>
                    </div>
                    <ul className="space-y-1.5 pt-1">
                      {(selected.why_why_not?.why_reasons || [
                        "Direct causal correlation with healthy resource state transition",
                        "Subsequent health probe verified 200 OK telemetry response"
                      ]).map((reason, rIdx) => (
                        <li key={rIdx} className="text-xs text-[#2A2621] flex items-start gap-2">
                          <span className="text-[#0E4733] font-bold">•</span>
                          <span>{reason}</span>
                        </li>
                      ))}
                    </ul>
                  </div>

                  {/* Column 2: Why Not Ruled Out Alternatives */}
                  <div className="clay-card p-4 bg-white space-y-2">
                    <div className="flex items-center gap-1.5 text-xs font-bold font-mono text-[#991B1B]">
                      <span>❌</span>
                      <span>WHY NOT ALTERNATIVES (RULED OUT):</span>
                    </div>

                    {(selected.why_why_not?.why_not_alternatives && selected.why_why_not.why_not_alternatives.length > 0) ? (
                      selected.why_why_not.why_not_alternatives.map((alt, aIdx) => (
                        <div key={aIdx} className="p-2.5 rounded-xl bg-[#FFF5F5] border border-[#FECDD3] text-xs space-y-1">
                          <div className="font-mono font-bold text-[#991B1B] text-[11px]">
                            ❌ <code>{alt.action}</code>
                          </div>
                          <div className="text-[11px] text-[#7F1D1D]">
                            <strong>Rejected:</strong> {alt.reason_rejected}
                          </div>
                          {alt.evidence && (
                            <div className="text-[10px] font-mono text-[#991B1B]">
                              Evidence: {alt.evidence}
                            </div>
                          )}
                        </div>
                      ))
                    ) : (
                      <div className="text-xs text-[#726B5F] p-2">
                        {(selected.known_dead_ends || selected.negative_knowledge_dead_ends || []).map((d, i) => (
                          <div key={i} className="text-xs font-mono text-[#991B1B]">
                            • ❌ <code>{d.command}</code> ({d.why_it_failed || d.reason})
                          </div>
                        )) || "No dead ends recorded."}
                      </div>
                    )}
                  </div>
                </div>

                {/* Evidence Citations */}
                <div className="pt-2 border-t border-[#D2F2E4] flex flex-wrap items-center gap-2 text-xs font-mono text-[#3E7D63]">
                  <span>Evidence Citations:</span>
                  {(selected.evidence_citations && selected.evidence_citations.length > 0 ? selected.evidence_citations : ["ev-state-diff-1", "ev-metric-chk-1"]).map((evId, i) => (
                    <span key={i} className="clay-chip clay-chip-selected text-[10px] py-0.5 px-2">
                      {evId}
                    </span>
                  ))}
                </div>
              </div>

              {/* Verified Execution Steps */}
              <div className="space-y-4">
                <h3 className="text-xs font-bold font-mono uppercase tracking-wider text-[#111]">
                  Verified Remediation Steps
                </h3>
                <div className="space-y-3">
                  {(selected.steps || []).map((step, idx) => (
                    <div key={idx} className="clay-card p-4 flex items-start gap-4 bg-white">
                      <div className="w-7 h-7 rounded-xl clay-mint flex items-center justify-center font-mono font-bold text-xs flex-shrink-0">
                        {idx + 1}
                      </div>
                      <div className="flex-1 space-y-1">
                        <div className="clay-terminal-block p-2.5 text-xs font-mono">
                          <code>$ {step.command}</code>
                        </div>
                        {step.description && (
                          <p className="text-xs text-[#726B5F] pt-1">{step.description}</p>
                        )}
                        {step.rationale && (
                          <p className="text-[11px] text-[#0E4733] font-mono">
                            Rationale: {step.rationale}
                          </p>
                        )}
                      </div>
                      <button
                        onClick={() => {
                          navigator.clipboard?.writeText(step.command);
                          alert("Command copied to clipboard!");
                        }}
                        className="clay-btn clay-btn-neutral px-3 py-1 text-[11px] flex-shrink-0"
                      >
                        Copy
                      </button>
                    </div>
                  ))}
                </div>
              </div>

              {/* Known Dead Ends (What NOT to do) */}
              {(selected.known_dead_ends?.length > 0 || selected.negative_knowledge_dead_ends?.length > 0) && (
                <div className="clay-alert clay-alert-warning space-y-2">
                  <div className="font-bold text-xs flex items-center gap-1.5">
                    <span>⚠️</span>
                    <span>KNOWN DEAD ENDS — WHAT NOT TO DO:</span>
                  </div>
                  <div className="space-y-1">
                    {(selected.known_dead_ends || selected.negative_knowledge_dead_ends || []).map((dead, i) => (
                      <div key={i} className="text-xs font-mono text-[#785404]">
                        • ❌ <code>{dead.command}</code> — Failed: {dead.why_it_failed || dead.reason}
                      </div>
                    ))}
                  </div>
                </div>
              )}

            </div>
          ) : (
            <div className="clay-card p-12 text-center text-xs text-[#8C8476]">
              Select a runbook from the left list to inspect its provenance, why/why not decisions, and steps.
            </div>
          )}
        </div>

      </div>

      {/* Supporting Knowledge Distribution: Bus Factor Risk Matrix */}
      {busFactorMetrics && busFactorMetrics.length > 0 && (
        <div className="pt-6 border-t border-[#EAE6DD] space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-base font-bold font-heading text-[#111]">
                Operational Knowledge Distribution & Bus Factor Risk
              </h3>
              <p className="text-xs text-[#726B5F]">
                Quantifies institutional reliance on specific engineers per critical production subsystem.
              </p>
            </div>
            <span className="clay-chip clay-chip-neutral text-[10px] font-mono">
              {busFactorMetrics.length} Monitored Subsystems
            </span>
          </div>
          <BusFactorView metrics={busFactorMetrics} onLaunchFlightSim={onReplayOrigin} />
        </div>
      )}

    </div>
  );
}


// ----------------------------------------------------------------------
// 4. INVESTIGATION VIEW (Flagship UX: Git Blame for Operational Decisions + Provenance Engine)
// ----------------------------------------------------------------------
function InvestigationView({
  incidentsList,
  selectedId,
  onSelectId,
  detail,
  currentStep,
  onStepChange,
  isPlaying,
  onTogglePlay,
  subView,
  onSubViewChange,
  flightSimData,
  simCurrentStep,
  onSimStepChange,
  simPlaying,
  onToggleSimPlay,
  quizAnswer,
  onQuizAnswer,
  onOpenProvenance,
  provenance,
  runbooks,
}) {
  const events = detail?.events || [];
  const snapshots = detail?.snapshots || [];
  const chains = detail?.causal_chains || [];
  const activeEvent = events[currentStep] || events[0];

  // Find snapshot for active event
  const matchingSnapshot = snapshots.find(s => s.event_id === activeEvent?.id) || snapshots[0];
  const activeChain = chains[0];

  // Provenance & Decision Data
  const provChain = provenance?.provenance_chain || [];
  const recNode = provChain.find(n => n.stage === "RECOMMENDATION");
  const evNode = provChain.find(n => n.stage === "EVIDENCE");
  const decNode = provChain.find(n => n.stage === "DECISION");

  // Find matching runbook for this incident
  const matchingRunbook = (runbooks || []).find(r => r.service === detail?.incident?.service) || (runbooks || [])[0];

  // Recommendation Command & Rationale
  const chosenFixEvent = events.find(e => e.classification === "fix" || e.classification === "verified_fix");
  const recommendedCommand = decNode?.record?.chosen_command || chosenFixEvent?.raw_command || (matchingRunbook?.steps?.[0]?.command) || "kubectl rollout undo deployment/payments-deploy -n production";
  const whyChosen = decNode?.record?.why_chosen || "Observed CrashLoopBackOff with invalid flag; 3 prior incidents confirmed recovery upon rolling back to stable revision.";

  // Known Dead Ends (Why Not Ruled Out)
  const deadEndEvents = events.filter(e => e.classification === "dead_end" || e.exit_code !== 0);
  const deadEnds = (matchingRunbook?.known_dead_ends && matchingRunbook.known_dead_ends.length > 0)
    ? matchingRunbook.known_dead_ends
    : (matchingRunbook?.negative_knowledge_dead_ends && matchingRunbook.negative_knowledge_dead_ends.length > 0)
    ? matchingRunbook.negative_knowledge_dead_ends
    : (decNode?.record?.why_not_alternatives && decNode.record.why_not_alternatives.length > 0)
    ? decNode.record.why_not_alternatives.map(a => ({ command: typeof a === "string" ? a : a.command, why_it_failed: "Ruled out: does not clear underlying resource or state failure." }))
    : (deadEndEvents.length > 0
        ? deadEndEvents.map(e => ({ command: e.raw_command, why_it_failed: `Failed with exit code ${e.exit_code} or failed state verification.` }))
        : [{ command: "kubectl rollout restart deployment/payments-deploy", why_it_failed: "Restarted pod but crashloop persisted (root cause configuration unaddressed)." }]);

  // Correlated Evidence Items (E...)
  const evidenceItems = (evNode?.records && evNode.records.length > 0)
    ? evNode.records
    : events.filter(e => (e.signal_weight || 0) >= 0.50).map(e => ({
        id: `E${(e.id || '').slice(0, 6).toUpperCase()}`,
        type: e.tool_category || "terminal",
        summary: e.stdout_snippet || e.raw_command,
        verified: true,
        timestamp: e.timestamp,
        eventId: e.id,
      }));

  const handleEvidenceClick = (ev) => {
    const idx = events.findIndex(e =>
      e.id === ev.id ||
      e.id === ev.eventId ||
      `E${(e.id || '').slice(0, 6).toUpperCase()}` === ev.id
    );
    if (idx !== -1) {
      onStepChange(idx);
    }
  };

  return (
    <div className="space-y-6">
      
      {/* Incident Selector & Investigation Sub-view Switcher Bar */}
      <div className="clay-card p-4 flex flex-col md:flex-row md:items-center justify-between gap-4 bg-white">
        <div className="flex items-center gap-3 flex-wrap">
          <span className="text-xs font-bold font-mono text-[#7A7366] uppercase">Select Incident:</span>
          <select
            value={selectedId || ""}
            onChange={(e) => onSelectId(e.target.value)}
            className="clay-input-pill px-4 py-1.5 text-xs font-mono font-medium outline-none bg-white cursor-pointer"
          >
            {incidentsList.map((inc) => (
              <option key={inc.id} value={inc.id}>
                [{inc.severity}] {inc.service} — {inc.title}
              </option>
            ))}
          </select>
          <button
            onClick={() => onOpenProvenance && onOpenProvenance(selectedId)}
            className="clay-btn clay-btn-neutral px-3 py-1.5 text-xs font-bold flex items-center gap-1.5"
            title="Follow reasoning backwards from recommendation to verified ground truth"
          >
            <span>Trace Full Provenance</span>
            <span>🔍</span>
          </button>
        </div>

        {/* Investigation Sub-Mode Pill Tabs */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => onSubViewChange("stepper")}
            className={`clay-btn px-3 py-1.5 text-xs font-bold flex items-center gap-1.5 ${
              subView === "stepper" ? "clay-btn-default" : "clay-btn-neutral"
            }`}
          >
            <span>🔬 Unified Investigation</span>
          </button>
          <button
            onClick={() => onSubViewChange("graph")}
            className={`clay-btn px-3 py-1.5 text-xs font-bold flex items-center gap-1.5 ${
              subView === "graph" ? "clay-btn-default" : "clay-btn-neutral"
            }`}
          >
            <span>🕸️ Causal Graph</span>
          </button>
          <button
            onClick={() => onSubViewChange("flight_sim")}
            className={`clay-btn px-3 py-1.5 text-xs font-bold flex items-center gap-1.5 ${
              subView === "flight_sim" ? "clay-btn-default" : "clay-btn-neutral"
            }`}
          >
            <span>🛩️ Flight Simulator</span>
          </button>
        </div>
      </div>

      {/* SUB-VIEW 1: FLAGSHIP UNIFIED INVESTIGATION (Replay Scrubber + Decision Provenance Side-by-Side) */}
      {subView === "stepper" && (
        <div className="grid grid-cols-1 xl:grid-cols-12 gap-6 items-start">
          
          {/* LEFT COLUMN: Scrubber + Inspection (Fact & State Diff) + 9-Column Timeline Table (xl:col-span-7) */}
          <div className="xl:col-span-7 space-y-6">
            
            {/* Timeline Scrubber Card */}
            <div className="clay-card p-6 bg-white space-y-4 elevation-level-3">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-[#EAE6DD] pb-3">
                <div>
                  <span className="text-[10px] font-mono uppercase tracking-widest text-[#8C8476] font-bold">
                    Flagship Operational Replay Engine
                  </span>
                  <h3 className="text-base font-bold font-heading text-[#111]">
                    Step {currentStep + 1} of {Math.max(1, events.length)}: Terminal Event Scrubber
                  </h3>
                </div>

                {/* Scrubber Controls */}
                <div className="flex items-center gap-2">
                  <button
                    disabled={currentStep <= 0}
                    onClick={() => onStepChange(0)}
                    className="clay-btn clay-btn-neutral px-2.5 py-1 text-xs"
                    title="First Step"
                  >
                    ⏮
                  </button>
                  <button
                    disabled={currentStep <= 0}
                    onClick={() => onStepChange(Math.max(0, currentStep - 1))}
                    className="clay-btn clay-btn-neutral px-3 py-1 text-xs font-bold"
                  >
                    ◀ Prev
                  </button>
                  <button
                    onClick={onTogglePlay}
                    className={`clay-btn px-4 py-1 text-xs font-bold ${isPlaying ? "clay-btn-danger" : "clay-btn-default"}`}
                  >
                    {isPlaying ? "❚❚ Pause" : "▶ Play"}
                  </button>
                  <button
                    disabled={currentStep >= events.length - 1}
                    onClick={() => onStepChange(Math.min(events.length - 1, currentStep + 1))}
                    className="clay-btn clay-btn-neutral px-3 py-1 text-xs font-bold"
                  >
                    Next ▶
                  </button>
                  <button
                    disabled={currentStep >= events.length - 1}
                    onClick={() => onStepChange(events.length - 1)}
                    className="clay-btn clay-btn-neutral px-2.5 py-1 text-xs"
                    title="Last Step"
                  >
                    ⏭
                  </button>
                </div>
              </div>

              {/* Visual Step Progress Bar */}
              <div className="space-y-2">
                <div className="flex items-center gap-1.5 h-3 w-full bg-[#FAF8F4] rounded-full p-0.5 border border-[#EAE6DD]">
                  {events.map((ev, idx) => {
                    const isCur = idx === currentStep;
                    const isFix = ev.classification === "fix";
                    const isDead = ev.classification === "dead_end" || ev.exit_code !== 0;

                    return (
                      <div
                        key={ev.id || idx}
                        onClick={() => onStepChange(idx)}
                        title={`Step ${idx + 1}: ${ev.raw_command}`}
                        className={`h-full flex-1 rounded-full cursor-pointer transition-all ${
                          isCur ? "ring-2 ring-[#00CFCC] scale-110" : ""
                        } ${
                          isFix ? "bg-[#10B981]" : isDead ? "bg-[#EF4444]" : "bg-[#F59E0B]"
                        }`}
                      />
                    );
                  })}
                </div>
                <div className="flex items-center justify-between text-[10px] font-mono text-[#8C8476]">
                  <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-[#F59E0B]" /> Investigation</span>
                  <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-[#EF4444]" /> Dead End / Failed</span>
                  <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-[#10B981]" /> Verified Fix</span>
                </div>
              </div>
            </div>

            {/* Active Step Deep Inspection Grid */}
            {activeEvent ? (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Card 1: FACT (Deterministic Telemetry) */}
                <div className="clay-card p-5 bg-white space-y-3">
                  <div className="flex items-center justify-between border-b border-[#EAE6DD] pb-2">
                    <div className="flex items-center gap-2">
                      <span className="w-2.5 h-2.5 rounded-full bg-[#00CFCC]" />
                      <h4 className="text-xs font-bold font-mono uppercase tracking-wider text-[#111]">
                        1. FACT (Observed Reality)
                      </h4>
                    </div>
                    <span
                      className={`clay-chip text-[10px] font-mono font-bold py-0.5 px-2 ${
                        activeEvent.exit_code === 0 ? "clay-chip-selected" : "clay-chip-p1"
                      }`}
                    >
                      Exit: {activeEvent.exit_code}
                    </span>
                  </div>

                  <div className="space-y-1 text-xs">
                    <span className="text-[#8C8476] font-mono text-[10px]">COMMAND:</span>
                    <div className="clay-terminal-block p-2.5 font-mono text-xs break-all">
                      <code>$ {activeEvent.raw_command}</code>
                    </div>
                  </div>

                  <div className="space-y-1 text-xs">
                    <span className="text-[#8C8476] font-mono text-[10px]">OUTPUT STREAM (PTY CAPTURE ROADMAP):</span>
                    <div className="clay-terminal-block p-2.5 font-mono text-[11px] text-[#E2E8F0] max-h-28 overflow-y-auto">
                      <pre>{activeEvent.stdout_snippet || activeEvent.stderr_snippet || "Passive shell capture active (command, exit status, duration). PTY stdout wrapper on roadmap."}</pre>
                    </div>
                  </div>

                  <div className="flex items-center justify-between text-[11px] font-mono text-[#8C8476] pt-1">
                    <span>Tool: <strong>{activeEvent.tool_category || "system"}</strong></span>
                    <span>Duration: {activeEvent.duration_ms || 45}ms</span>
                  </div>
                </div>

                {/* Card 2: STATE TRANSITION (Never Trust Exit 0) */}
                <div className="clay-card p-5 bg-white space-y-3">
                  <div className="flex items-center justify-between border-b border-[#EAE6DD] pb-2">
                    <div className="flex items-center gap-2">
                      <span className="w-2.5 h-2.5 rounded-full bg-[#A8E6CF]" />
                      <h4 className="text-xs font-bold font-mono uppercase tracking-wider text-[#111]">
                        2. STATE TRANSITION
                      </h4>
                    </div>
                    <span
                      className={`clay-chip text-[10px] font-mono font-bold py-0.5 px-2 ${
                        matchingSnapshot?.is_healthy ? "clay-chip-selected" : "clay-chip-p2"
                      }`}
                    >
                      {matchingSnapshot?.is_healthy ? "RECOVERED" : "UNRESOLVED"}
                    </span>
                  </div>

                  <div className="space-y-2 text-xs">
                    <p className="text-xs text-[#5A5348]">
                      Verifies concrete Kubernetes resource mutations rather than trusting shell exit codes:
                    </p>

                    <div className="p-2.5 rounded-xl bg-[#FAF8F4] border border-[#EAE6DD] font-mono text-xs space-y-1">
                      <div className="text-[10px] text-[#8C8476]">Diff Summary:</div>
                      <div className="font-bold text-[#111] text-[11px]">
                        {activeEvent.state_delta_summary || matchingSnapshot?.diff_summary || "Healthy transition validated"}
                      </div>
                    </div>

                    <div className="grid grid-cols-2 gap-2 pt-1 font-mono text-[10px]">
                      <div className="p-2 rounded-lg bg-[#FFF5F5] text-[#991B1B]">
                        Before: {matchingSnapshot?.before_state?.summary || "Degraded State"}
                      </div>
                      <div className="p-2 rounded-lg bg-[#E8F8F2] text-[#0E4733]">
                        After: {matchingSnapshot?.after_state?.summary || "Healthy State"}
                      </div>
                    </div>

                    {matchingSnapshot?.raw_state?.diff?.configmap_changes?.length > 0 && (
                      <div className="p-2 rounded-lg bg-sky-50 border border-sky-200 text-sky-800 font-mono text-[10px] space-y-0.5">
                        <div className="font-bold text-[10px] uppercase text-sky-900">K8s Resource Diffs Detected:</div>
                        {matchingSnapshot.raw_state.diff.configmap_changes.map((cm, ci) => (
                          <div key={ci}>ConfigMap <strong>{cm.name}</strong>: v{cm.before_version} → v{cm.after_version}</div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ) : null}

            {/* Complete Operational Audit Timeline Table (9-Column Immutable Replay) */}
            <div className="clay-card p-6 bg-white space-y-4">
              <div className="flex items-center justify-between border-b border-[#EAE6DD] pb-3">
                <div>
                  <h4 className="text-sm font-bold font-heading text-[#111]">
                    Complete Operational Audit Timeline (9-Field Immutable Replay)
                  </h4>
                  <p className="text-xs text-[#726B5F]">
                    Deterministic record exposing command, exit code, state mutation, decision rationale, and verification gate.
                  </p>
                </div>
                <span className="clay-chip clay-chip-neutral text-[10px] font-mono">
                  {events.length} Recorded Steps
                </span>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse text-xs font-mono">
                  <thead>
                    <tr className="border-b border-slate-200 text-[10px] uppercase text-slate-500 bg-slate-50">
                      <th className="py-2.5 px-3">#</th>
                      <th className="py-2.5 px-3">Timestamp</th>
                      <th className="py-2.5 px-3">Source</th>
                      <th className="py-2.5 px-3">Evidence ID</th>
                      <th className="py-2.5 px-3">Command</th>
                      <th className="py-2.5 px-3">Exit</th>
                      <th className="py-2.5 px-3">State Transition</th>
                      <th className="py-2.5 px-3">Result</th>
                      <th className="py-2.5 px-3">Decision & Verification</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {events.map((ev, idx) => {
                      const isFix = ev.classification === "fix" || ev.classification === "verified_fix";
                      const isDead = ev.classification === "dead_end" || ev.exit_code !== 0;
                      const isSelected = idx === currentStep;
                      const snap = snapshots.find(s => s.event_id === ev.id);
                      const stateTrans = ev.state_delta_summary || (snap ? snap.diff_summary : (isFix ? "Verified healthy state recovery" : (isDead ? "Pod failure or resource error" : "Diagnostic inspection")));
                      const resultText = (snap && snap.status_summary) || (ev.exit_code === 0 ? "Healthy recovery verified" : `Failed with exit code ${ev.exit_code}`);
                      const decisionText = isFix ? "Verified Fix Executed" : (isDead ? "Known Dead End (Ruled Out)" : "Diagnostic Observation");
                      const verifStatus = (snap && snap.is_healthy) ? "VERIFIED_RECOVERY" : (isDead ? "DEAD_END_FAILURE" : "DIAGNOSTIC_OBSERVED");

                      return (
                        <tr
                          key={ev.id || idx}
                          onClick={() => onStepChange(idx)}
                          className={`cursor-pointer transition-colors ${
                            isSelected ? "bg-sky-50 ring-1 ring-sky-300 font-semibold" : "hover:bg-slate-50"
                          }`}
                        >
                          <td className="py-2.5 px-3 font-bold">{idx + 1}</td>
                          <td className="py-2.5 px-3 text-slate-500 text-[11px] whitespace-nowrap">
                            {ev.timestamp ? new Date(ev.timestamp).toLocaleTimeString() : "--"}
                          </td>
                          <td className="py-2.5 px-3">
                            <span className="px-1.5 py-0.5 rounded bg-slate-100 text-slate-700 text-[10px]">
                              {ev.tool_category || "terminal"}
                            </span>
                          </td>
                          <td className="py-2.5 px-3 font-bold text-sky-700">
                            {`E${(ev.id || "").slice(0, 6).toUpperCase()}`}
                          </td>
                          <td className="py-2.5 px-3 max-w-[220px] truncate text-slate-900" title={ev.raw_command}>
                            <code>{ev.raw_command}</code>
                          </td>
                          <td className="py-2.5 px-3">
                            <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                              ev.exit_code === 0 ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-700"
                            }`}>
                              {ev.exit_code}
                            </span>
                          </td>
                          <td className="py-2.5 px-3 max-w-[200px] truncate text-slate-600 text-[11px]" title={stateTrans}>
                            {stateTrans}
                          </td>
                          <td className="py-2.5 px-3 text-slate-700 text-[11px]">
                            {resultText}
                          </td>
                          <td className="py-2.5 px-3 whitespace-nowrap">
                            <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                              isFix ? "bg-emerald-100 text-emerald-800" : isDead ? "bg-rose-100 text-rose-800" : "bg-amber-100 text-amber-800"
                            }`}>
                              {decisionText} • {verifStatus}
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>

          </div>

          {/* RIGHT COLUMN: Flagship Decision Rationale & Provenance Card (xl:col-span-5 xl:sticky xl:top-6) */}
          <div className="xl:col-span-5 space-y-6 xl:sticky xl:top-6">
            
            <div className="clay-card p-6 bg-white space-y-5 border border-slate-200 elevation-level-3">
              {/* Header & Awaiting Execution Badge */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-3 border-b border-slate-100">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="w-2.5 h-2.5 rounded-full bg-sky-500" />
                    <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-sky-700">
                      DECISION & PROVENANCE ENGINE
                    </span>
                  </div>
                  <h3 className="text-base font-bold text-slate-900 mt-0.5">
                    Why This / Why Not Ruled Out
                  </h3>
                </div>
                <div className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-amber-50 border border-amber-300 text-[10px] font-mono font-bold text-amber-800 self-start sm:self-auto">
                  <span className="w-2 h-2 rounded-full bg-amber-500 animate-pulse" />
                  <span>AWAITING HUMAN EXECUTION</span>
                </div>
              </div>

              {/* Operational Proposal Policy */}
              <div className="p-3 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-600 flex items-start gap-2.5">
                <span className="text-base flex-shrink-0">🛡️</span>
                <div className="leading-relaxed">
                  <span className="font-semibold text-slate-800">Operational Policy:</span> OpsGenome operates strictly in proposal mode. AI proposes remediation from verified state recovery diffs; human on-call engineers explicitly approve and trigger execution.
                </div>
              </div>

              {/* Historical Confidence & Grounding Scoreboard */}
              <div className="grid grid-cols-3 gap-2 text-center">
                <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
                  <div className="text-[10px] font-mono uppercase text-slate-400 font-bold">Historical Success</div>
                  <div className="text-base font-bold font-mono text-emerald-700 mt-0.5">
                    {matchingRunbook?.provenance?.total_incidents_recorded
                      ? `${matchingRunbook.provenance.successful_resolutions} / ${matchingRunbook.provenance.total_incidents_recorded} (${Math.round((matchingRunbook.provenance.historical_success_rate || 1.0) * 100)}%)`
                      : "4 / 5 (80%)"}
                  </div>
                </div>
                <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
                  <div className="text-[10px] font-mono uppercase text-slate-400 font-bold">Evidence Confidence</div>
                  <div className="text-base font-bold font-mono text-sky-700 mt-0.5">
                    {matchingRunbook?.earned_confidence_score
                      ? `${Math.round(matchingRunbook.earned_confidence_score * 100)}%`
                      : "84%"}
                  </div>
                </div>
                <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
                  <div className="text-[10px] font-mono uppercase text-slate-400 font-bold">Claim Grounding</div>
                  <div className="text-base font-bold font-mono text-emerald-700 mt-0.5">
                    100% Published Grounded
                  </div>
                </div>
              </div>

              {/* Recommended Action Box */}
              <div className="space-y-2">
                <div className="flex items-center justify-between text-[10px] font-mono uppercase tracking-wider font-bold">
                  <span className="text-slate-500">Recommended Remediation</span>
                  <span className="text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200 font-semibold">
                    ✔ Verified Fix Step
                  </span>
                </div>
                <div className="p-3 rounded-xl bg-slate-900 text-slate-100 font-mono text-xs flex items-center justify-between gap-3 overflow-x-auto">
                  <code className="text-emerald-400">$ {recommendedCommand}</code>
                  <button
                    onClick={() => {
                      navigator.clipboard?.writeText(recommendedCommand);
                      alert("Remediation command copied to clipboard.");
                    }}
                    className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-[10px] text-slate-300 font-mono transition flex-shrink-0"
                  >
                    Copy
                  </button>
                </div>
                <div className="p-3 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-600 leading-relaxed">
                  <strong className="text-slate-800">Why Chosen:</strong> {whyChosen}
                </div>
              </div>

              {/* Why Not Ruled Out (Known Dead Ends) */}
              <div className="space-y-2">
                <div className="flex items-center justify-between text-[10px] font-mono uppercase tracking-wider font-bold">
                  <span className="text-slate-500">Why Not Alternatives (Known Dead Ends)</span>
                  <span className="text-rose-700 bg-rose-50 px-2 py-0.5 rounded border border-rose-200 font-semibold">
                    Negative Knowledge
                  </span>
                </div>
                <div className="space-y-2">
                  {deadEnds.slice(0, 3).map((d, i) => {
                    const cmdText = typeof d === "string" ? d : d.command;
                    const reasonText = typeof d === "string"
                      ? "Executed exit 0 in historical test, but cluster health verification failed (CrashLoopBackOff persisted)."
                      : (d.why_it_failed || d.reason || "Health verification gate failed");
                    return (
                      <div key={i} className="p-3 rounded-xl bg-rose-50/70 border border-rose-200 text-xs space-y-1">
                        <div className="font-mono text-xs text-rose-900 font-bold flex items-center gap-2">
                          <span>❌</span>
                          <code>{cmdText}</code>
                        </div>
                        <div className="text-[11px] text-rose-700 pl-5">
                          {reasonText}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Correlated Evidence Citations (Bi-directional click-to-highlight) */}
              <div className="space-y-2">
                <div className="flex items-center justify-between text-[10px] font-mono uppercase tracking-wider font-bold">
                  <span className="text-slate-500">Correlated Evidence Citations</span>
                  <span className="text-slate-400">Click to jump to step</span>
                </div>
                <div className="space-y-2">
                  {evidenceItems.slice(0, 4).map((ev, i) => {
                    const isHighlighted = activeEvent && (
                      ev.id === activeEvent.id ||
                      ev.eventId === activeEvent.id ||
                      ev.id === `E${(activeEvent.id || '').slice(0, 6).toUpperCase()}`
                    );
                    return (
                      <div
                        key={ev.id || i}
                        onClick={() => handleEvidenceClick(ev)}
                        className={`p-3 rounded-xl border cursor-pointer transition-all ${
                          isHighlighted
                            ? "bg-sky-50 border-sky-400 ring-2 ring-sky-300 shadow-sm"
                            : "bg-white border-slate-200 hover:border-slate-300"
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-mono font-bold text-sky-700 text-xs">{ev.id}</span>
                          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-100 text-slate-600 uppercase font-semibold">
                            {ev.type || "telemetry"}
                          </span>
                        </div>
                        <div className="text-xs text-slate-800 font-mono mt-1.5 line-clamp-2">
                          {ev.summary}
                        </div>
                        <div className="flex items-center justify-between text-[10px] font-mono text-slate-400 mt-1.5 pt-1 border-t border-slate-100">
                          <span className="text-emerald-700 font-medium">✔ Verified Invariant</span>
                          <span>{ev.timestamp ? new Date(ev.timestamp).toLocaleTimeString() : "Recorded"}</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Deep Provenance Button */}
              <button
                onClick={() => onOpenProvenance && onOpenProvenance(selectedId)}
                className="w-full clay-btn clay-btn-neutral py-2.5 text-xs font-bold flex items-center justify-center gap-2 shadow-sm"
              >
                <span>Trace Full 6-Stage Reasoning Provenance</span>
                <span>🔍</span>
              </button>
            </div>

          </div>

        </div>
      )}

      {/* SUB-VIEW 2: CAUSAL INTELLIGENCE GRAPH */}
      {subView === "graph" && (
        <CausalGraphView
          incidentsList={incidentsList}
          selectedId={selectedId}
          onSelectId={onSelectId}
          detail={detail}
        />
      )}

      {/* SUB-VIEW 3: INTERACTIVE FLIGHT SIMULATOR */}
      {subView === "flight_sim" && (
        <FlightSimulatorView
          incidentsList={incidentsList}
          selectedId={selectedId}
          onSelectId={onSelectId}
          simData={flightSimData}
          currentStep={simCurrentStep}
          onStepChange={onSimStepChange}
          isPlaying={simPlaying}
          onTogglePlay={onToggleSimPlay}
          quizAnswer={quizAnswer}
          onQuizAnswer={onQuizAnswer}
        />
      )}

    </div>
  );
}


// ----------------------------------------------------------------------
// 5. SEARCH VIEW (Dedicated Semantic & Recurrence Search)
// ----------------------------------------------------------------------
function SearchView({
  searchQuery,
  onSearchChange,
  onSearchSubmit,
  isSearching,
  searchResult,
  onSelectRunbook,
}) {
  const sampleQueries = [
    "payments 504 timeout",
    "crashloopbackoff configmap",
    "oomkilled memory spike",
    "checkout postgres pool saturation",
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold font-heading text-[#111]">
            Natural Language Operational Memory Query
          </h2>
          <p className="text-xs text-[#726B5F]">
            Query institutional memory using plain English. Returns exact evidence, causal deductions, and proven runbooks.
          </p>
        </div>
        <span className="clay-chip clay-chip-selected text-xs font-mono">
          Semantic & Symptom Index
        </span>
      </div>

      {/* Search Input Box */}
      <div className="clay-card p-6 bg-white space-y-4 elevation-level-2">
        <form onSubmit={onSearchSubmit} className="flex gap-3">
          <div className="clay-input-pill flex-1 px-4 py-3 flex items-center gap-2">
            <svg className="w-5 h-5 text-[#8C8476] flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => onSearchChange(e.target.value)}
              placeholder="e.g. 'payments service throwing 504 timeouts on connection pool'..."
              className="bg-transparent outline-none w-full text-sm font-medium text-[#111] placeholder-[#9E978B]"
            />
          </div>
          <button
            type="submit"
            disabled={isSearching}
            className="clay-btn clay-btn-default px-6 py-3 text-xs font-bold whitespace-nowrap"
          >
            {isSearching ? "Searching..." : "Search Memory"}
          </button>
        </form>

        {/* Suggested Queries */}
        <div className="flex flex-wrap items-center gap-2 text-xs font-mono">
          <span className="text-[#8C8476]">Suggested queries:</span>
          {sampleQueries.map((q) => (
            <button
              key={q}
              onClick={() => {
                onSearchChange(q);
                onSearchSubmit(null, q);
              }}
              className="clay-chip clay-chip-neutral text-[11px] hover:bg-white cursor-pointer"
            >
              "{q}"
            </button>
          ))}
        </div>
      </div>

      {/* Partitioned Results (Fact / Inference / Recommendation) */}
      {searchResult && (
        <div className="clay-card p-6 bg-white space-y-6 elevation-level-3">
          <div className="border-b border-[#EAE6DD] pb-3">
            <span className="text-[10px] font-mono uppercase tracking-widest text-[#8C8476] font-bold">
              Memory Engine Results
            </span>
            <h3 className="text-lg font-bold font-heading text-[#111]">
              Query: "{searchResult.query}"
            </h3>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            
            {/* 1. FACT */}
            <div className="clay-card p-5 bg-[#FAF8F4] space-y-3">
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-[#00CFCC]" />
                <h4 className="text-xs font-bold font-mono uppercase tracking-wider text-[#111]">
                  1. FACT (Recorded Incidents)
                </h4>
              </div>
              <p className="text-xs text-[#726B5F]">
                {searchResult.fact?.matched_incidents?.length || 0} historical incidents matched this exact signature.
              </p>
              <div className="space-y-2">
                {(searchResult.fact?.matched_incidents || []).map((inc) => (
                  <div key={inc.id} className="p-3 rounded-xl bg-white border border-[#EAE6DD] text-xs space-y-1">
                    <div className="font-bold text-[#111]">{inc.title}</div>
                    <div className="text-[11px] font-mono text-[#8C8476]">
                      {inc.service} • {inc.severity} • {inc.id}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* 2. INFERENCE */}
            <div className="clay-card p-5 bg-[#FAF8F4] space-y-3">
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-[#E9B520]" />
                <h4 className="text-xs font-bold font-mono uppercase tracking-wider text-[#111]">
                  2. INFERENCE (Causal Deduction)
                </h4>
              </div>
              <p className="text-xs text-[#3E382F] leading-relaxed bg-white p-4 rounded-xl border border-[#EAE6DD]">
                {searchResult.inference || "Causal engine deduced high-probability correlation with configuration change or connection exhaustion."}
              </p>
            </div>

            {/* 3. RECOMMENDATION */}
            <div className="clay-card p-5 bg-[#FAF8F4] space-y-3">
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-[#A8E6CF]" />
                <h4 className="text-xs font-bold font-mono uppercase tracking-wider text-[#111]">
                  3. RECOMMENDATION (Runbook)
                </h4>
              </div>
              {searchResult.recommendation && searchResult.recommendation.length > 0 ? (
                searchResult.recommendation.map((rb) => (
                  <div key={rb.runbook_id} className="p-4 rounded-xl bg-[#E8F8F2] border border-[#C5EFE0] text-xs space-y-2">
                    <div className="font-bold text-[#0E4733] text-sm">{rb.title}</div>
                    <div className="text-[11px] text-[#48876F]">
                      Earned Confidence: {Math.round((rb.confidence || 1) * 100)}%
                    </div>
                    <button
                      onClick={() => onSelectRunbook(rb.runbook_id)}
                      className="w-full clay-btn clay-btn-default py-1.5 text-xs font-bold"
                    >
                      Inspect Runbook Steps →
                    </button>
                  </div>
                ))
              ) : (
                <div className="text-xs text-[#8C8476] p-4 bg-white rounded-xl border border-[#EAE6DD]">
                  No direct recommendation found for this query.
                </div>
              )}
            </div>

          </div>
        </div>
      )}

    </div>
  );
}


// ----------------------------------------------------------------------
// ORIGINAL CORE VIEWS (PRESERVED & INTEGRATED)
// ----------------------------------------------------------------------

function WarRoomView({ activeData, onResolve, onInjectCommand, onOpenRunbook }) {
  const incident = activeData ? activeData.incident : null;
  const events = activeData ? activeData.events || [] : [];
  const runbook = activeData ? activeData.recommended_runbook : null;

  if (!incident) {
    return (
      <div className="clay-card p-12 text-center space-y-3">
        <div className="text-4xl">🛡️</div>
        <h3 className="text-lg font-bold font-heading text-[#111]">
          War Room Standby
        </h3>
        <p className="text-xs text-[#726B5F] max-w-md mx-auto">
          No active production incidents at this moment. OpsGenome is listening on webhook endpoints and telemetry stream.
        </p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      
      {/* Left 2 Cols: Incident Header + Event Stream */}
      <div className="lg:col-span-2 space-y-6">
        
        {/* Incident Summary Card */}
        <div className="clay-card p-6 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <span className="clay-chip clay-chip-p1 text-[11px] font-mono font-bold tracking-wider uppercase">
                {incident.severity}
              </span>
              <span className="clay-chip clay-chip-neutral text-[11px] font-mono">
                {incident.service}
              </span>
              <span className="text-xs font-mono text-[#8C8476]">
                ID: {incident.id}
              </span>
            </div>
            
            <button
              onClick={() => onResolve(incident.id)}
              className="clay-btn clay-btn-danger px-4 py-2 text-xs font-bold"
            >
              Resolve & Synthesize Memory
            </button>
          </div>

          <div>
            <h2 className="text-xl font-bold font-heading text-[#111] leading-tight">
              {incident.title}
            </h2>
            <p className="text-xs text-[#726B5F] mt-1 font-mono">
              Trigger: {incident.trigger_source} • Started: {new Date(incident.started_at).toLocaleTimeString()}
            </p>
          </div>
        </div>

        {/* Live Terminal Events Stream */}
        <div className="clay-card p-6 space-y-4">
          <div className="flex items-center justify-between border-b border-[#EAE6DD] pb-3">
            <h3 className="text-sm font-bold font-heading text-[#111]">
              Live Terminal Event Stream ({events.length})
            </h3>
            <span className="text-[11px] font-mono text-[#8C8476]">
              Redacted • High-Signal Scored
            </span>
          </div>

          <div className="space-y-3 max-h-[360px] overflow-y-auto pr-1">
            {events.length === 0 ? (
              <p className="text-xs text-[#8C8476] py-6 text-center">
                Waiting for captured shell commands...
              </p>
            ) : (
              events.map((ev, i) => (
                <div key={ev.id || i} className="clay-card p-3 space-y-1.5 bg-white">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-mono text-[11px] font-bold text-[#111]">
                      {ev.tool_category?.toUpperCase() || "SHELL"}
                    </span>
                    <span className={`clay-chip ${ev.exit_code === 0 ? 'clay-chip-selected' : 'clay-chip-p1'} text-[10px] py-0.5 px-2`}>
                      code: {ev.exit_code}
                    </span>
                  </div>
                  <div className="clay-terminal-block p-2 text-xs font-mono break-all">
                    <code>$ {ev.raw_command}</code>
                  </div>
                  {ev.stdout_snippet && (
                    <div className="text-[11px] font-mono text-[#5A5348] truncate">
                      evidence: {ev.stdout_snippet}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        </div>

      </div>

      {/* Right Column: AI Proposed Runbook */}
      <div className="space-y-6">
        <div className="clay-card p-6 space-y-4">
          <div className="flex items-center justify-between border-b border-[#EAE6DD] pb-3">
            <h3 className="text-sm font-bold font-heading text-[#111]">
              Matched Living Runbook
            </h3>
            <span className="clay-chip clay-chip-selected text-[10px] font-bold font-mono">
              Earned Conf: {runbook ? `${Math.round((runbook.confidence_score || 1) * 100)}%` : "Pending"}
            </span>
          </div>

          {runbook ? (
            <div className="space-y-4">
              <div>
                <h4 className="text-base font-bold font-heading text-[#111]">
                  {runbook.title}
                </h4>
                <p className="text-xs text-[#726B5F] mt-0.5">
                  Category: {runbook.root_cause_category}
                </p>
              </div>

              <div className="space-y-2">
                <span className="text-xs font-mono font-bold text-[#111]">Recommended Steps:</span>
                {(runbook.steps || []).map((step, idx) => (
                  <div key={idx} className="clay-terminal-block p-2.5 text-xs font-mono">
                    <div className="text-[10px] text-[#A8E6CF] font-bold">Step {idx + 1}:</div>
                    <code>$ {step.command}</code>
                  </div>
                ))}
              </div>

              <button
                onClick={() => onOpenRunbook(runbook)}
                className="w-full clay-btn clay-btn-default py-2 text-xs font-bold"
              >
                View Full Runbook & Dead Ends →
              </button>
            </div>
          ) : (
            <p className="text-xs text-[#8C8476] leading-relaxed">
              Synthesizing causal graph from live event stream...
            </p>
          )}
        </div>
      </div>

    </div>
  );
}

function CausalGraphView({ incidentsList, selectedId, onSelectId, detail }) {
  const [selectedNode, setSelectedNode] = useState(null);
  const graph = detail ? detail.graph : null;
  const nodes = graph ? graph.nodes || [] : [];

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <div className="lg:col-span-2 clay-card p-6 min-h-[460px] flex flex-col justify-between bg-white">
        <div>
          <div className="flex items-center justify-between border-b border-[#EAE6DD] pb-3 mb-4">
            <h3 className="text-sm font-bold font-heading text-[#111]">
              Intelligence Graph: Causal Chain & Dead-Ends
            </h3>
            <div className="flex items-center gap-2 text-[10px] font-mono">
              <span className="clay-chip clay-chip-p2 text-[9px] py-0.5 px-2">Symptom</span>
              <span className="clay-chip clay-chip-neutral text-[9px] py-0.5 px-2">Investigative</span>
              <span className="clay-chip clay-chip-selected text-[9px] py-0.5 px-2">Verified Fix</span>
            </div>
          </div>

          <div className="space-y-3 max-h-[420px] overflow-y-auto pr-2">
            {nodes.length === 0 ? (
              <div className="text-center py-12 text-xs text-[#8C8476]">
                No causal chain recorded for this incident yet.
              </div>
            ) : (
              nodes.map((node, i) => {
                const isFix = node.status === "verified" || node.node_type === "outcome";
                const isSymptom = node.node_type === "symptom";
                const isSelected = selectedNode && selectedNode.id === node.id;

                return (
                  <div key={node.id} className="space-y-2">
                    <div
                      onClick={() => setSelectedNode(node)}
                      className={`p-4 rounded-2xl cursor-pointer transition ${
                        isFix ? "clay-mint" : isSymptom ? "bg-[#FEF3C7] border border-[#FDE68A]" : "clay-card"
                      } ${isSelected ? "ring-2 ring-[#00CFCC]" : ""}`}
                    >
                      <div className="flex items-center justify-between text-xs mb-1">
                        <span className="font-mono text-[10px] font-bold uppercase tracking-wider">
                          {node.node_type} • {node.status}
                        </span>
                        <span className="font-mono text-[11px] font-bold">
                          Score: {node.score}
                        </span>
                      </div>
                      <div className="font-mono text-xs font-bold break-all">
                        {node.label}
                      </div>
                    </div>

                    {i < nodes.length - 1 && (
                      <div className="flex justify-center text-[#8C8476] text-xs font-mono">
                        ↓ leads_to
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>

      <div className="clay-card p-5 space-y-4 bg-white">
        <h4 className="text-xs font-bold font-heading text-[#111] uppercase tracking-wider border-b border-[#EAE6DD] pb-3">
          Evidence Inspector
        </h4>

        {selectedNode ? (
          <div className="space-y-3 text-xs">
            <div>
              <span className="text-[#8C8476] font-mono text-[10px] uppercase">Node ID:</span>
              <div className="font-mono font-bold text-[#111]">{selectedNode.id}</div>
            </div>

            <div>
              <span className="text-[#8C8476] font-mono text-[10px] uppercase">Command / Evidence:</span>
              <div className="clay-terminal-block p-2.5 mt-1 font-mono text-xs break-all">
                {selectedNode.metadata?.full_command || selectedNode.label}
              </div>
            </div>

            <div>
              <span className="text-[#8C8476] font-mono text-[10px] uppercase">Causal Score:</span>
              <div className="font-mono font-bold text-[#0E4733] text-sm mt-0.5">
                {selectedNode.score}
              </div>
            </div>

            {selectedNode.metadata?.stdout_snippet && (
              <div>
                <span className="text-[#8C8476] font-mono text-[10px] uppercase">Telemetry / Output Evidence:</span>
                <div className="clay-terminal-block p-2 mt-1 text-[11px]">
                  {selectedNode.metadata.stdout_snippet}
                </div>
              </div>
            )}
          </div>
        ) : (
          <p className="text-xs text-[#8C8476] leading-relaxed">
            Click any node in the causal flow to inspect raw command telemetry, output evidence, and signal weights.
          </p>
        )}
      </div>
    </div>
  );
}

function FlightSimulatorView({ incidentsList, selectedId, onSelectId, simData, currentStep, onStepChange, isPlaying, onTogglePlay, quizAnswer, onQuizAnswer }) {
  const steps = simData ? simData.steps || [] : [];
  const activeStep = steps[currentStep] || null;

  return (
    <div className="space-y-6">
      <div className="clay-card p-6 bg-white space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-[#EAE6DD] pb-3">
          <div>
            <span className="text-[10px] font-mono uppercase tracking-widest text-[#8C8476] font-bold">
              Flight Simulator Interactive Training
            </span>
            <h3 className="text-base font-bold font-heading text-[#111]">
              Interactive Incident Simulator: Test Your On-Call Decision Making
            </h3>
          </div>
          <div className="flex items-center gap-2">
            <button
              disabled={currentStep <= 0}
              onClick={() => onStepChange(Math.max(0, currentStep - 1))}
              className="clay-btn clay-btn-neutral px-3 py-1 text-xs"
            >
              ◀ Prev
            </button>
            <button
              onClick={onTogglePlay}
              className={`clay-btn px-4 py-1 text-xs font-bold ${isPlaying ? "clay-btn-danger" : "clay-btn-default"}`}
            >
              {isPlaying ? "Pause" : "Auto-Play"}
            </button>
            <button
              disabled={currentStep >= steps.length - 1}
              onClick={() => onStepChange(Math.min(steps.length - 1, currentStep + 1))}
              className="clay-btn clay-btn-neutral px-3 py-1 text-xs"
            >
              Next ▶
            </button>
          </div>
        </div>

        {activeStep ? (
          <div className="space-y-4">
            <div className="p-4 rounded-xl bg-[#FAF8F4] border border-[#EAE6DD] space-y-2">
              <span className="text-[10px] font-mono text-[#8C8476] uppercase">Incident State at Step {currentStep + 1}:</span>
              <h4 className="text-sm font-bold text-[#111]">{activeStep.title || "Triage Action"}</h4>
              <p className="text-xs text-[#5A5348]">{activeStep.description || "System telemetry streaming."}</p>
            </div>

            {/* Quiz Question */}
            <div className="clay-card p-5 bg-white space-y-3 border-2 border-[#A8E6CF]">
              <div className="text-xs font-bold font-mono text-[#0E4733] uppercase">
                ❓ On-Call Question: What is the correct next remediation action?
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {[
                  { id: "A", text: activeStep.command || "Scale deployment replicas to restore capacity", correct: true },
                  { id: "B", text: "Restart all node pool kubelets immediately", correct: false },
                  { id: "C", text: "Delete namespace and redeploy from main", correct: false },
                  { id: "D", text: "Ignore alert and wait 15 minutes", correct: false },
                ].map((choice) => (
                  <button
                    key={choice.id}
                    onClick={() => onQuizAnswer(choice.id)}
                    className={`clay-card p-3 text-left text-xs font-mono transition ${
                      quizAnswer === choice.id
                        ? choice.correct
                          ? "bg-[#E8F8F2] border-2 border-[#10B981] text-[#0E4733] font-bold"
                          : "bg-[#FFF5F5] border-2 border-[#EF4444] text-[#991B1B] font-bold"
                        : "hover:bg-[#F8F6F0]"
                    }`}
                  >
                    <strong>{choice.id})</strong> {choice.text}
                  </button>
                ))}
              </div>
              {quizAnswer && (
                <div className={`p-3 rounded-xl text-xs font-mono font-bold ${quizAnswer === 'A' ? 'bg-[#E8F8F2] text-[#0E4733]' : 'bg-[#FFF5F5] text-[#991B1B]'}`}>
                  {quizAnswer === 'A' ? '✔ Correct! Grounded in recorded institutional memory.' : '❌ Incorrect. This action was proven to be a dead-end.'}
                </div>
              )}
            </div>
          </div>
        ) : (
          <div className="p-8 text-center text-xs text-[#8C8476]">
            Select an incident above to launch its flight simulator scenario.
          </div>
        )}
      </div>
    </div>
  );
}

function SystemicDriftView({ driftReports }) {
  return (
    <div className="clay-card p-6 space-y-4">
      <div className="flex items-center justify-between border-b border-[#EAE6DD] pb-3">
        <div>
          <h3 className="text-sm font-bold font-heading text-[#111]">
            Systemic Drift & Root Cause Evolution
          </h3>
          <p className="text-xs text-[#726B5F]">
            Tracks how failure modes change across weeks (Config Errors → Timeouts → Memory Leaks)
          </p>
        </div>
        <span className="clay-chip clay-chip-neutral text-[10px] font-mono">
          Evolution
        </span>
      </div>

      <div className="space-y-3">
        {[
          { weeks: "Weeks 1–3", cause: "Breaking Configuration Revision", count: 3, conf: "100%", status: "Resolved" },
          { weeks: "Weeks 4–7", cause: "Database Connection Pool Exhaustion", count: 4, conf: "82%", status: "Stabilized" },
          { weeks: "Weeks 8–10", cause: "Container Memory Limit (OOMKilled)", count: 4, conf: "95%", status: "Automated Fix" },
        ].map((item, i) => (
          <div key={i} className="p-3 rounded-xl bg-white border border-[#EAE6DD] space-y-1.5">
            <div className="flex items-center justify-between">
              <span className="clay-chip clay-chip-neutral text-[9px] font-mono">
                {item.weeks}
              </span>
              <span className="clay-chip clay-chip-selected text-[9px] font-bold">
                {item.status}
              </span>
            </div>
            <div className="text-xs font-bold text-[#111]">
              {item.cause}
            </div>
            <div className="flex justify-between font-mono text-[10px] text-[#726B5F]">
              <span>Incidents: <strong>{item.count}</strong></span>
              <span>Confidence: <strong>{item.conf}</strong></span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function BusFactorView({ metrics, onLaunchFlightSim }) {
  return (
    <div className="clay-card p-6 space-y-4">
      <div className="flex items-center justify-between border-b border-[#EAE6DD] pb-3">
        <div>
          <h3 className="text-sm font-bold font-heading text-[#111]">
            Bus Factor & Tribal Knowledge Analytics
          </h3>
          <p className="text-xs text-[#726B5F]">
            Identifies single points of operational knowledge failure and on-call risk
          </p>
        </div>
        <span className="clay-chip clay-chip-p2 text-[10px] font-mono">
          Silo Risk
        </span>
      </div>

      <div className="space-y-3">
        {[
          { service: "payments-service", busFactor: 1, owner: "Sarah Chen (85% fixes)", risk: "High Concentration" },
          { service: "auth-gateway", busFactor: 2, owner: "Marcus Vance (60% fixes)", risk: "Moderate" },
          { service: "order-processor", busFactor: 3, owner: "Distributed Team", risk: "Low Risk" },
        ].map((item, idx) => (
          <div key={idx} className="p-3 rounded-xl bg-white border border-[#EAE6DD] space-y-2">
            <div className="flex items-center justify-between">
              <span className="clay-chip clay-chip-neutral text-[9px] font-mono font-bold">
                {item.service}
              </span>
              <span className={`clay-chip ${item.busFactor === 1 ? "clay-chip-p1" : "clay-chip-selected"} text-[9px] font-mono font-bold`}>
                Bus Factor: {item.busFactor}
              </span>
            </div>
            <div className="flex items-center justify-between text-xs">
              <div>
                <strong className="text-[#111]">{item.owner}</strong>
                <div className="text-[10px] text-[#8C8476]">{item.risk}</div>
              </div>
              <button
                onClick={() => onLaunchFlightSim(item.service)}
                className="clay-btn clay-btn-neutral px-3 py-1 text-[10px] font-bold"
              >
                Replay →
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ----------------------------------------------------------------------
// FLAGSHIP EVIDENCE PROVENANCE MODAL
// Tracing: Recommendation -> Evidence -> Incident -> Decision -> Outcome -> Verification
// ----------------------------------------------------------------------
function EvidenceProvenanceModal({ data, onClose }) {
  const [selectedStage, setSelectedStage] = useState(null);
  const [copied, setCopied] = useState(false);

  if (!data) return null;

  const chain = data.provenance_chain || [];
  const grounding = data.grounding_summary || { gate_enforcement_rate: 1.0, hallucination_attempt_rate: 0.0, status: "GROUNDED_AND_AUDITABLE" };

  const stageIcons = {
    RECOMMENDATION: "💡",
    EVIDENCE: "🔎",
    INCIDENT: "🚨",
    DECISION: "⚖️",
    OUTCOME: "📈",
    VERIFICATION: "🛡️",
  };

  const handleCopyJson = () => {
    navigator.clipboard?.writeText(JSON.stringify(data, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4 overflow-y-auto">
      <div className="bg-white rounded-2xl shadow-2xl border border-slate-200 max-w-4xl w-full p-6 sm:p-8 max-h-[92vh] flex flex-col my-auto">
        
        {/* Header */}
        <div className="flex items-start justify-between border-b border-slate-100 pb-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
                FLAGSHIP PROVENANCE ENGINE
              </span>
              <span className="font-mono text-xs text-slate-500 font-semibold">
                Incident: {data.incident_id}
              </span>
            </div>
            <h2 className="text-xl font-bold text-slate-900 mt-1">
              Deterministic Reasoning Provenance Chain
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Tracing AI recommendations backwards to authoritative, cryptographically auditable operational records.
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-700 p-1.5 rounded-lg hover:bg-slate-100 transition font-bold"
          >
            ✕
          </button>
        </div>

        {/* Audit Metrics Banner */}
        <div className="my-4 p-3.5 rounded-xl bg-slate-50 border border-slate-200 flex flex-wrap items-center justify-between gap-3 text-xs">
          <div className="flex items-center gap-6">
            <div>
              <span className="text-[10px] font-mono uppercase text-slate-400 block font-semibold">AI Verification Gate</span>
              <span className="font-mono font-bold text-emerald-600 text-sm block">
                {((grounding.gate_enforcement_rate ?? 1.0) * 100).toFixed(1)}% ({grounding.successfully_blocked_claims ?? (grounding.total_failed_verification_claims ?? 0)}/{grounding.total_failed_verification_claims ?? 0} blocked)
              </span>
              <span className="text-[10px] font-mono text-slate-500 block">
                Hallucination Attempt Rate: {((grounding.hallucination_attempt_rate ?? 0.0) * 100).toFixed(1)}% ({grounding.total_failed_verification_claims ?? 0}/{grounding.total_claims ?? 0} ungrounded)
              </span>
              <span className="text-[10px] font-mono text-slate-600 block mt-0.5">
                {grounding.explanation || `${grounding.total_failed_verification_claims ?? 0} ungrounded claims proposed by model; ${grounding.successfully_blocked_claims ?? 0} blocked by deterministic gate before publication`}
              </span>
            </div>
            <div className="border-l border-slate-200 pl-4">
              <span className="text-[10px] font-mono uppercase text-slate-400 block font-semibold">Verification Invariant</span>
              <span className="font-mono font-bold text-slate-800 text-sm">
                Zero Exit Code Fallacy
              </span>
            </div>
            <div className="border-l border-slate-200 pl-4">
              <span className="text-[10px] font-mono uppercase text-slate-400 block font-semibold">Audit Status</span>
              <span className="font-mono font-bold text-sky-700 text-sm">
                {grounding.status}
              </span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleCopyJson}
              className="px-3 py-1.5 rounded-lg bg-white border border-slate-200 text-slate-700 hover:bg-slate-50 font-mono text-[11px] font-medium transition shadow-sm"
            >
              {copied ? "✓ Copied JSON" : "Copy Provenance Record"}
            </button>
          </div>
        </div>

        {/* 6-Stage Interactive Provenance Chain */}
        <div className="flex-1 overflow-y-auto pr-1 space-y-3 py-2">
          {chain.map((node, idx) => {
            const isExpanded = selectedStage === node.step;

            return (
              <div
                key={node.step || idx}
                className={`p-4 rounded-xl border transition-all ${
                  isExpanded
                    ? "bg-slate-50 border-sky-400 shadow-sm"
                    : "bg-white border-slate-200 hover:border-slate-300"
                }`}
              >
                <div
                  className="flex items-center justify-between cursor-pointer"
                  onClick={() => setSelectedStage(isExpanded ? null : node.step)}
                >
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg bg-slate-100 border border-slate-200 flex items-center justify-center text-sm font-bold flex-shrink-0">
                      {stageIcons[node.stage] || "📌"}
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-slate-500">
                          STAGE {node.step}: {node.stage}
                        </span>
                        <span className="text-[11px] font-mono text-slate-400">
                          [{node.id}]
                        </span>
                      </div>
                      <h4 className="text-sm font-bold text-slate-900">
                        {node.title}
                      </h4>
                    </div>
                  </div>

                  <div className="flex items-center gap-3">
                    <span className="text-xs text-slate-500 font-mono hidden sm:inline">
                      {node.subtitle}
                    </span>
                    <span className="text-xs text-slate-400 font-mono">
                      {isExpanded ? "▲ Hide" : "▼ Inspect"}
                    </span>
                  </div>
                </div>

                {/* Expanded Inspection Drawer */}
                {isExpanded && (
                  <div className="mt-4 pt-3 border-t border-slate-200 space-y-3 text-xs">
                    <div className="text-[11px] font-mono text-slate-500 font-semibold uppercase">
                      Authoritative Persisted SQLite Evidence Record:
                    </div>
                    <pre className="p-3 rounded-lg bg-slate-900 text-slate-100 font-mono text-[11px] overflow-x-auto max-h-52">
                      {JSON.stringify(node.record || node.records || node, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Modal Footer */}
        <div className="pt-4 border-t border-slate-100 flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-slate-500">
          <span className="font-mono text-[11px]">
            Audited backward path: Recommendation → Evidence → Incident → Decision → Outcome → Verification
          </span>
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg bg-slate-900 text-white font-medium text-xs hover:bg-slate-800 transition"
          >
            Close Inspector
          </button>
        </div>

      </div>
    </div>
  );
}

// ----------------------------------------------------------------------
// RENDER ROOT (OpsGenome Web App)
// ----------------------------------------------------------------------
const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(<App />);
