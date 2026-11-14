import {
  Suspense,
  lazy,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  ArrowDownRight,
  ArrowUpRight,
  Box,
  ChevronDown,
  CircleHelp,
  Crosshair,
  Download,
  Gauge,
  Layers2,
  Pause,
  Play,
  RotateCcw,
  Settings2,
  Thermometer,
  X,
} from "lucide-react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
const Scene = lazy(() => import("./Scene"));
import {
  defaults,
  display,
  indexAt,
  type Config,
  type Result,
  type Sample,
} from "./types";
import "./style.css";

const navigation = [
  "Simulation Lab",
  "PID Comparison",
  "Digital Twin",
  "Fault Laboratory",
  "Learn",
  "Results",
];
const faults: Record<string, string> = {
  none: "No disturbance",
  sensor_bias: "Sensor bias +2 °C",
  sensor_drift: "Sensor drift",
  noise: "Sensor noise",
  cold_inlet: "Cold inlet −3 °C",
  flow: "Cold flow +30%",
  degradation: "Heat transfer −30%",
  stuck: "Stuck valve",
};
const lessons = [
  [
    "Meet the exchanger",
    "Drag to orbit. Select Cutaway to reveal the illustrative tube bundle. Hot and cold streams exchange heat across a wall.",
  ],
  [
    "Follow the heat",
    "Press play and follow the warm and cool paths. The boiler is an imposed inlet-temperature boundary.",
  ],
  [
    "Change the target",
    "Raise the setpoint and run a new simulation. Watch the measured outlet follow the target.",
  ],
  [
    "Proportional action",
    "Select P and run. A persistent offset can remain because proportional action requires error to hold the valve open.",
  ],
  [
    "Integral action",
    "Select PI and rerun. Integral action accumulates error and can reduce steady-state offset.",
  ],
  [
    "Derivative action",
    "Select PID. Derivative on measurement responds to the rate of temperature change; noise can make it sensitive.",
  ],
  [
    "Add a disturbance",
    "Choose a cold inlet or flow disturbance and observe the recovery.",
  ],
  [
    "Meet the twin",
    "Open Digital Twin to compare a separately fitted model with the simulated process.",
  ],
  [
    "Try a fault",
    "Inject sensor bias or a stuck valve. The residual alarm indicates an anomaly, not its cause.",
  ],
];
const componentInfo: Record<string, [string, string]> = {
  exchanger: [
    "HX-101 · Heat exchanger",
    "Two mixed-fluid temperatures exchange heat through an effective conductance. The internal geometry is illustrative, not CFD.",
  ],
  valve: [
    "TV-101 · Control valve",
    "The visible handle follows actual simulated valve position. Command and actual position differ because the actuator has a time constant.",
  ],
  source: [
    "Heat source · Boundary",
    "Illustrative only. The model imposes an 80 °C hot inlet; boiler dynamics are not simulated.",
  ],
  sensor: [
    "TT-102 · Temperature sensor",
    "The sensor reports the cold outlet temperature, with any injected bias, drift, or noise. Its signal closes the feedback loop.",
  ],
  pump: [
    "Cold-side pump",
    "Illustrative equipment. The model specifies cold-side mass flow directly and does not model pump dynamics.",
  ],
};
const empty: Sample = {
  time: 0,
  tc: 54.87,
  th: 63.8,
  valve: 0.4,
  setpoint: 54.87,
  measurement: 54.87,
  command: 0.4,
  tc_in: 30,
  ua: 350,
  mc: 0.03,
  fault_active: false,
  twin: 54.87,
  residual: 0,
  alarm: false,
  hot_flow: 0.046,
  heat_w: 3000,
};
function App() {
  const [config, setConfig] = useState<Config>(defaults),
    [result, setResult] = useState<Result | null>(null),
    [tab, setTab] = useState("Simulation Lab"),
    [time, setTime] = useState(0),
    [playing, setPlaying] = useState(false),
    [speed, setSpeed] = useState(4),
    [loading, setLoading] = useState(false),
    [error, setError] = useState(""),
    [cutaway, setCutaway] = useState(true),
    [exploded, setExploded] = useState(false),
    [selected, setSelected] = useState("exchanger"),
    [resetKey, setResetKey] = useState(0),
    [focusKey, setFocusKey] = useState(0),
    [lesson, setLesson] = useState(0),
    [panel, setPanel] = useState(true),
    [dirty, setDirty] = useState(false),
    [series, setSeries] = useState("PID"),
    [chartMode, setChartMode] = useState<"temperature" | "output">(
      "temperature",
    );
  const raf = useRef<number>(0),
    last = useRef<number | null>(null);
  const change = <K extends keyof Config>(key: K, value: Config[K]) => {
    setConfig((c) => ({ ...c, [key]: value }));
    setDirty(true);
  };
  const run = useCallback(async (settings: Config) => {
    setLoading(true);
    setError("");
    setPlaying(false);
    try {
      const response = await fetch("/api/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(settings),
      });
      if (!response.ok)
        throw new Error(`Simulation request failed (${response.status})`);
      const data: Result = await response.json();
      setResult(data);
      setSeries(settings.compare ? "PID" : settings.controller);
      setTime(0);
      setDirty(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Simulation unavailable");
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    void run(defaults);
  }, [run]);
  useEffect(() => {
    if (!playing || !result) {
      last.current = null;
      return;
    }
    const tick = (stamp: number) => {
      if (last.current !== null) {
        const elapsed = (stamp - last.current) / 1000;
        setTime((t) => {
          const next = t + elapsed * speed;
          if (next >= config.duration) {
            setPlaying(false);
            return config.duration;
          }
          return next;
        });
      }
      last.current = stamp;
      raf.current = requestAnimationFrame(tick);
    };
    raf.current = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(raf.current);
      last.current = null;
    };
  }, [playing, speed, result, config.duration]);
  const chosen = result?.runs[series] || Object.values(result?.runs || {})[0];
  const sample = chosen?.samples[indexAt(time, chosen.samples.length)] || empty;
  const history = useMemo(() => {
    if (!result || !chosen) return [];
    const max = indexAt(time, chosen.samples.length);
    return chosen.samples
      .slice(0, max + 1)
      .filter((_, i) => i % 2 === 0 || i === max)
      .map((s) => {
        const row: Record<string, number> = {
          time: s.time,
          tc: s.tc,
          setpoint: s.setpoint,
          twin: s.twin,
          command: s.command * 100,
          valve: s.valve * 100,
          residual: s.residual,
        };
        if (config.compare)
          for (const k of ["P", "PI", "PID"])
            row[k] = result.runs[k]?.samples[s.time]?.tc;
        return row;
      });
  }, [result, chosen, time, config.compare]);
  const switchTab = (name: string) => {
    setTab(name);
    if (name === "PID Comparison" && !config.compare) {
      change("compare", true);
    }
  };
  const exportCsv = () => {
    if (!chosen) return;
    const keys = Object.keys(chosen.samples[0]);
    const text = [
      keys.join(","),
      ...chosen.samples.map((s) =>
        keys.map((k) => String(s[k as keyof Sample])).join(","),
      ),
    ].join("\n");
    const url = URL.createObjectURL(new Blob([text], { type: "text/csv" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `heatwin-${series.toLowerCase()}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };
  if (!result)
    return (
      <div className="startup">
        <div className="brand-mark">
          <Activity size={18} />
        </div>
        <h1>HEATWIN</h1>
        <p>
          {error
            ? "Simulation API unavailable. Start the Python server and retry."
            : "Preparing the simulation laboratory…"}
        </p>
        {error && (
          <button className="dark" onClick={() => void run(config)}>
            Retry connection
          </button>
        )}
      </div>
    );
  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">
            <Activity size={18} />
          </span>
          <span>
            HEATWIN<small>PROCESS CONTROL LAB</small>
          </span>
        </div>
        <nav>
          {navigation.map((n) => (
            <button
              key={n}
              className={tab === n ? "active" : ""}
              onClick={() => switchTab(n)}
            >
              {n}
            </button>
          ))}
        </nav>
        <div className="header-right">
          <span className="live-dot" /> SIMULATION{" "}
          <span className="header-index">NIT JALANDHAR&nbsp; / &nbsp;01</span>
        </div>
      </header>
      <main>
        <div className="page-head">
          <div>
            <div className="eyebrow">
              <span>●</span> INTERACTIVE ENGINEERING LAB <b>/</b> MODULE 01
            </div>
            <h1>{tab === "Simulation Lab" ? "The heat exchanger" : tab}</h1>
            <p>Explore the process. Adjust the control. See the response.</p>
          </div>
          <div className="head-actions">
            <button className="outline" onClick={() => setPanel(!panel)}>
              <Settings2 size={15} /> {panel ? "Hide" : "Show"} controls
            </button>
            <button className="dark" onClick={() => setTab("Learn")}>
              <CircleHelp size={15} /> Experience PID <span>↗</span>
            </button>
          </div>
        </div>
        <div className={`workspace ${panel ? "" : "no-panel"}`}>
          {panel && (
            <aside className="control-panel panel">
              <div className="panel-head">
                <div>
                  <span className="micro">01 / CONFIGURATION</span>
                  <h2>Control station</h2>
                </div>
                <Gauge size={19} />
              </div>
              <div className="section-label">
                CONTROLLER <span>● ONLINE</span>
              </div>
              <div className="segmented">
                {["P", "PI", "PID"].map((m) => (
                  <button
                    key={m}
                    className={config.controller === m ? "selected" : ""}
                    onClick={() => change("controller", m)}
                  >
                    {m}
                  </button>
                ))}
              </div>
              <div className="field">
                <label>Operating mode</label>
                <select
                  aria-label="Operating mode"
                  value={config.mode}
                  onChange={(e) => change("mode", e.target.value)}
                >
                  <option value="auto">Automatic feedback</option>
                  <option value="manual">Manual valve command</option>
                </select>
              </div>
              {config.mode === "manual" && (
                <NumberField
                  label="Manual valve"
                  unit="fraction"
                  value={config.manual_valve}
                  step={0.05}
                  onChange={(v) => change("manual_valve", v)}
                />
              )}
              <div className="field">
                <label>Tuning method</label>
                <select
                  aria-label="Tuning method"
                  value={config.tuning}
                  onChange={(e) => change("tuning", e.target.value)}
                >
                  <option value="manual">Manual tuning</option>
                  <option value="imc">IMC</option>
                  <option value="zn">Ziegler–Nichols</option>
                  <option value="cohen-coon">Cohen–Coon</option>
                </select>
              </div>
              <div className="divider" />
              <div className="section-label">
                PROCESS TARGET <span>°C</span>
              </div>
              <div className="setpoint">
                <div>
                  <small>Cold outlet setpoint</small>
                  <strong>
                    {display(config.setpoint, 1)}
                    <em>°C</em>
                  </strong>
                </div>
                <span className="setpoint-icon">
                  <Thermometer size={20} />
                </span>
              </div>
              <input
                aria-label="Setpoint"
                type="range"
                min="35"
                max="70"
                step=".5"
                value={config.setpoint}
                onChange={(e) => change("setpoint", Number(e.target.value))}
              />
              <div className="range-label">
                <span>35 °C</span>
                <span>70 °C</span>
              </div>
              <div className="divider" />
              <div className="section-label">
                PID PARAMETERS <span>PARALLEL FORM</span>
              </div>
              <div className="gain-grid">
                <NumberField
                  label="Kp"
                  unit="1/°C"
                  value={config.kp}
                  step={0.01}
                  onChange={(v) => change("kp", v)}
                />
                <NumberField
                  label="Ki"
                  unit="1/°C·s"
                  value={config.ki}
                  step={0.001}
                  onChange={(v) => change("ki", v)}
                />
                <NumberField
                  label="Kd"
                  unit="s/°C"
                  value={config.kd}
                  step={0.01}
                  onChange={(v) => change("kd", v)}
                />
              </div>
              <div className="divider" />
              <div className="field">
                <label>Scenario / disturbance</label>
                <select
                  aria-label="Scenario / disturbance"
                  value={config.fault}
                  onChange={(e) => change("fault", e.target.value)}
                >
                  {Object.entries(faults).map(([k, v]) => (
                    <option value={k} key={k}>
                      {v}
                    </option>
                  ))}
                </select>
              </div>
              <div className="compact-fields">
                <NumberField
                  label="Inject at"
                  unit="s"
                  value={config.fault_time}
                  step={10}
                  onChange={(v) => change("fault_time", v)}
                />
                <NumberField
                  label="UA"
                  unit="W/K"
                  value={config.ua}
                  step={10}
                  onChange={(v) => change("ua", v)}
                />
              </div>
              <label className="check">
                <input
                  type="checkbox"
                  checked={config.compare}
                  onChange={(e) => change("compare", e.target.checked)}
                />{" "}
                Compare P / PI / PID
              </label>
              <button
                className="run-button"
                onClick={() => void run(config)}
                disabled={loading}
              >
                {loading
                  ? "SIMULATING…"
                  : dirty
                    ? "APPLY & RESTART"
                    : "RUN SIMULATION"}{" "}
                <span>↗</span>
              </button>
              <p className="aside-note">
                Changes apply on restart. Setpoint steps at 30 s; Python
                computes every sample.
              </p>
            </aside>
          )}
          <section className="center-column">
            <div className="viewport panel">
              <div className="viewport-top">
                <div>
                  <span className="micro">02 / PROCESS VISUALIZATION</span>
                  <div className="view-title">
                    Heat exchanger <span>HX-101</span>
                  </div>
                </div>
                <div className="view-status">
                  <span className="live-dot" /> {playing ? "RUNNING" : "PAUSED"}{" "}
                  <i /> t = {display(time, 0)} s
                </div>
              </div>
              <div className="canvas-wrap">
                <Suspense
                  fallback={
                    <div className="webgl-fallback">Loading 3D scene…</div>
                  }
                >
                  <Scene
                    sample={sample}
                    time={time}
                    cutaway={cutaway}
                    exploded={exploded}
                    selected={selected}
                    onSelect={setSelected}
                    resetKey={resetKey}
                    focusKey={focusKey}
                  />
                </Suspense>
                <div className="viewport-tools">
                  <button
                    className={cutaway ? "on" : ""}
                    onClick={() => setCutaway(!cutaway)}
                    title="Toggle transparent shell"
                  >
                    <Layers2 size={16} /> Cutaway
                  </button>
                  <button
                    className={exploded ? "on" : ""}
                    onClick={() => setExploded(!exploded)}
                    title="Explode end caps"
                  >
                    <Box size={16} /> Explode
                  </button>
                  <button
                    onClick={() => setFocusKey((k) => k + 1)}
                    title="Focus selected equipment"
                  >
                    Focus
                  </button>
                  <button
                    onClick={() => setResetKey((k) => k + 1)}
                    title="Reset camera"
                  >
                    <Crosshair size={16} />
                  </button>
                </div>
                <div className="view-hint">
                  DRAG TO ORBIT&nbsp;&nbsp; · &nbsp;&nbsp;SCROLL TO
                  ZOOM&nbsp;&nbsp; · &nbsp;&nbsp;CLICK EQUIPMENT
                </div>
                {tab === "Digital Twin" && (
                  <div className="twin-inset">
                    <span className="micro">SYNCHRONIZED COMPARISON</span>
                    <div>
                      <section>
                        <small>SIMULATED PLANT</small>
                        <strong>{display(sample.tc)} °C</strong>
                      </section>
                      <section>
                        <small>FOPDT TWIN</small>
                        <strong>{display(sample.twin)} °C</strong>
                      </section>
                    </div>
                    <p>
                      Residual: {display(sample.residual, 2)} °C · sensor − twin
                    </p>
                  </div>
                )}
                <div className="flow-legend">
                  <span>
                    <i className="hot" /> HOT SIDE
                  </span>
                  <span>
                    <i className="cold" /> COLD SIDE
                  </span>
                  <small>
                    Paths & internal geometry illustrative · not CFD
                  </small>
                </div>
              </div>
              <div className="loop-bar">
                <span>CONTROL LOOP</span>
                <b>SETPOINT</b>
                <i>→</i>
                <b>PID</b>
                <i>→</i>
                <b>VALVE</b>
                <i>→</i>
                <b>EXCHANGER</b>
                <i>→</i>
                <b>SENSOR</b>
                <i>↩</i>
                <b>FEEDBACK</b>
              </div>
            </div>
            <div className="chart-panel panel">
              <div className="chart-header">
                <div>
                  <span className="micro">03 / LIVE RESPONSE</span>
                  <h2>
                    {chartMode === "output"
                      ? "Valve command & position"
                      : tab === "Digital Twin"
                        ? "Plant vs. digital twin"
                        : tab === "Fault Laboratory"
                          ? "Residual monitoring"
                          : config.compare
                            ? "Controller comparison"
                            : "Temperature response"}
                  </h2>
                </div>
                <div className="chart-key">
                  <button
                    onClick={() =>
                      setChartMode(
                        chartMode === "temperature" ? "output" : "temperature",
                      )
                    }
                  >
                    {chartMode === "temperature"
                      ? "SHOW VALVE OUTPUT"
                      : "SHOW TEMPERATURE"}
                  </button>
                  <span>
                    <i className="key-dark" />{" "}
                    {chartMode === "output" ? "ACTUAL VALVE" : "OUTLET"}
                  </span>
                  <span>
                    <i className="key-orange" />{" "}
                    {chartMode === "output" ? "COMMAND" : "SETPOINT"}
                  </span>
                  {tab === "Digital Twin" && (
                    <span>
                      <i className="key-green" /> TWIN
                    </span>
                  )}
                </div>
              </div>
              <div className="chart">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart
                    data={history}
                    margin={{ top: 8, right: 18, left: -15, bottom: 0 }}
                  >
                    <CartesianGrid stroke="#e5e8e0" vertical={false} />
                    <XAxis
                      dataKey="time"
                      tick={{ fontSize: 10, fill: "#9ba49c" }}
                      tickLine={false}
                      axisLine={false}
                      unit="s"
                    />
                    <YAxis
                      domain={["auto", "auto"]}
                      tick={{ fontSize: 10, fill: "#9ba49c" }}
                      tickLine={false}
                      axisLine={false}
                    />
                    <Tooltip
                      contentStyle={{
                        fontSize: 12,
                        border: "1px solid #dce2d8",
                        borderRadius: 8,
                      }}
                    />
                    {chartMode === "output" ? (
                      <>
                        <Line
                          type="monotone"
                          dataKey="command"
                          stroke="#cf7950"
                          dot={false}
                          strokeWidth={2}
                        />
                        <Line
                          type="monotone"
                          dataKey="valve"
                          stroke="#263e37"
                          dot={false}
                          strokeWidth={2}
                        />
                      </>
                    ) : tab === "Fault Laboratory" ? (
                      <Line
                        type="monotone"
                        dataKey="residual"
                        stroke="#cf7950"
                        dot={false}
                        strokeWidth={2}
                      />
                    ) : (
                      <>
                        <Line
                          type="monotone"
                          dataKey="setpoint"
                          stroke="#d58d65"
                          strokeDasharray="4 4"
                          dot={false}
                          strokeWidth={1.5}
                        />
                        {config.compare && result?.runs.P ? (
                          <>
                            <Line dataKey="P" stroke="#cc7f54" dot={false} />
                            <Line dataKey="PI" stroke="#6f9f91" dot={false} />
                            <Line
                              dataKey="PID"
                              stroke="#243c37"
                              dot={false}
                              strokeWidth={2}
                            />
                          </>
                        ) : (
                          <Line
                            type="monotone"
                            dataKey="tc"
                            stroke="#263e37"
                            dot={false}
                            strokeWidth={2}
                          />
                        )}{" "}
                        {tab === "Digital Twin" && (
                          <Line
                            type="monotone"
                            dataKey="twin"
                            stroke="#79ae9a"
                            dot={false}
                            strokeWidth={2}
                          />
                        )}
                      </>
                    )}
                  </LineChart>
                </ResponsiveContainer>
              </div>
              <div className="playbar">
                <button
                  className="play"
                  aria-label={playing ? "Pause" : "Play"}
                  onClick={() => setPlaying(!playing)}
                >
                  {playing ? (
                    <Pause size={16} fill="currentColor" />
                  ) : (
                    <Play size={16} fill="currentColor" />
                  )}
                </button>
                <button
                  className="icon-button"
                  aria-label="Reset playback"
                  onClick={() => {
                    setTime(0);
                    setPlaying(false);
                  }}
                >
                  <RotateCcw size={16} />
                </button>
                <span>{display(time, 0)}s</span>
                <input
                  aria-label="Simulation timeline"
                  type="range"
                  min="0"
                  max={config.duration}
                  step="1"
                  value={time}
                  onChange={(e) => setTime(Number(e.target.value))}
                />
                <span>{config.duration}s</span>
                <select
                  aria-label="Playback speed"
                  value={speed}
                  onChange={(e) => setSpeed(Number(e.target.value))}
                >
                  <option value={1}>1×</option>
                  <option value={4}>4×</option>
                  <option value={10}>10×</option>
                  <option value={25}>25×</option>
                </select>
                <button
                  className="icon-button"
                  aria-label="Export CSV"
                  onClick={exportCsv}
                >
                  <Download size={16} />
                </button>
              </div>
            </div>
          </section>
          <aside className="instrument-panel panel">
            <div className="panel-head">
              <div>
                <span className="micro">04 / INSTRUMENTATION</span>
                <h2>Process readings</h2>
              </div>
              <Activity size={19} />
            </div>
            <div className="instrument-caption">
              LIVE SIMULATED VALUES <span>●</span>
            </div>
            <div className="reading-group">
              <div className="reading-title">
                <span className="temp-dot warm" /> HOT STREAM{" "}
                <ArrowUpRight size={14} />
              </div>
              <Reading label="Inlet temperature" value="80.0" unit="°C" />
              <Reading
                label="Outlet temperature"
                value={display(sample.th)}
                unit="°C"
              />
              <Reading
                label="Mass flow"
                value={display(sample.hot_flow, 3)}
                unit="kg/s"
              />
            </div>
            <div className="reading-group">
              <div className="reading-title">
                <span className="temp-dot cool" /> COLD STREAM{" "}
                <ArrowDownRight size={14} />
              </div>
              <Reading
                label="Inlet temperature"
                value={display(sample.tc_in)}
                unit="°C"
              />
              <Reading
                label="Outlet temperature"
                value={display(sample.tc)}
                unit="°C"
              />
              <Reading
                label="Mass flow"
                value={display(sample.mc, 3)}
                unit="kg/s"
              />
            </div>
            <div className="reading-group">
              <div className="reading-title">
                <span className="temp-dot neutral" /> CONTROL LOOP{" "}
                <Activity size={14} />
              </div>
              <Reading
                label="Control error"
                value={display(sample.setpoint - sample.measurement, 2)}
                unit="°C"
              />
              <Reading
                label="Valve command"
                value={display(sample.command * 100)}
                unit="%"
              />
              <Reading
                label="Valve position"
                value={display(sample.valve * 100)}
                unit="%"
              />
              <Reading
                label="Heat transfer"
                value={display(sample.heat_w / 1000, 2)}
                unit="kW"
              />
              <Reading
                label="Twin residual"
                value={display(sample.residual, 2)}
                unit="°C"
              />
            </div>
            <div className={`alarm ${sample.alarm ? "triggered" : ""}`}>
              <span>{sample.alarm ? "!" : "✓"}</span>
              <div>
                <b>{sample.alarm ? "Residual alarm" : "No residual alarm"}</b>
                <small>
                  {sample.alarm
                    ? "Anomaly detected; cause not identified."
                    : "Threshold 1 °C · 3 samples"}
                </small>
              </div>
            </div>
            <div className="component-card">
              <span className="micro">SELECTED COMPONENT</span>
              <h3>{componentInfo[selected][0]}</h3>
              <p>{componentInfo[selected][1]}</p>
            </div>
          </aside>
        </div>
        {(tab === "Learn" ||
          tab === "Results" ||
          tab === "PID Comparison" ||
          tab === "Digital Twin" ||
          tab === "Fault Laboratory") && (
          <section className="detail panel">
            <button
              className="detail-close"
              onClick={() => setTab("Simulation Lab")}
              aria-label="Close detail"
            >
              <X size={16} />
            </button>
            {tab === "Learn" ? (
              <>
                <span className="micro">
                  GUIDED LEARNING / {String(lesson + 1).padStart(2, "0")} OF 09
                </span>
                <h2>Experience PID Control</h2>
                <h3>{lessons[lesson][0]}</h3>
                <p>{lessons[lesson][1]}</p>
                <div className="lesson-actions">
                  <button
                    className="outline"
                    disabled={lesson === 0}
                    onClick={() => setLesson(lesson - 1)}
                  >
                    ← Previous
                  </button>
                  <button
                    className="dark"
                    disabled={lesson === 8}
                    onClick={() => setLesson(lesson + 1)}
                  >
                    Next experience →
                  </button>
                </div>
              </>
            ) : (
              <>
                <span className="micro">LAB NOTES / {tab.toUpperCase()}</span>
                <h2>{tab}</h2>
                {tab === "PID Comparison" && (
                  <>
                    <p>
                      Matched plant, setpoint and disturbance. Apply & restart
                      to run all three controllers; select a trajectory for the
                      3D view.
                    </p>
                    <div className="segmented select-series">
                      {["P", "PI", "PID"].map((m) => (
                        <button
                          key={m}
                          className={series === m ? "selected" : ""}
                          onClick={() => setSeries(m)}
                        >
                          {m}
                        </button>
                      ))}
                    </div>
                  </>
                )}
                {tab === "Digital Twin" && (
                  <p>
                    The twin is a separately fitted first-order-plus-dead-time
                    model. Its residual can reflect noise, faults, unmeasured
                    disturbances, or model mismatch.
                  </p>
                )}
                {tab === "Fault Laboratory" && (
                  <p>
                    Select a fault and injection time in the control station,
                    then apply & restart. The residual alarm cannot determine
                    the cause. A stuck valve may not be detected.
                  </p>
                )}
                {tab === "Results" && (
                  <p>
                    Metrics are evaluated from the setpoint change over the
                    finite run. A dash means the settling or rise threshold was
                    not reached.
                  </p>
                )}
                {config.compare && result?.runs.P && (
                  <div className="compare-table">
                    <table>
                      <thead>
                        <tr>
                          <th>Controller</th>
                          <th>IAE</th>
                          <th>ISE</th>
                          <th>ITAE</th>
                          <th>Overshoot °C</th>
                          <th>Settling s</th>
                          <th>Final error °C</th>
                          <th>Valve travel</th>
                        </tr>
                      </thead>
                      <tbody>
                        {["P", "PI", "PID"].map((name) => (
                          <tr key={name}>
                            <th>{name}</th>
                            {[
                              "IAE",
                              "ISE",
                              "ITAE",
                              "overshoot_C",
                              "settling_s",
                              "final_error_C",
                              "valve_travel",
                            ].map((k) => (
                              <td key={k}>
                                {result.runs[name].metrics[k] === null
                                  ? "—"
                                  : display(
                                      result.runs[name].metrics[k] ?? undefined,
                                      2,
                                    )}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                {chosen && (
                  <div className="metric-row">
                    {[
                      ["IAE", "°C·s"],
                      ["ISE", "°C²·s"],
                      ["ITAE", "°C·s²"],
                      ["overshoot_C", "°C"],
                      ["settling_s", "s"],
                      ["rise_90_s", "s"],
                      ["final_error_C", "°C"],
                      ["valve_travel", "fraction"],
                    ].map(([k, u]) => (
                      <div key={k}>
                        <small>{k.replaceAll("_", " ")}</small>
                        <strong>
                          {chosen.metrics[k] === null
                            ? "—"
                            : display(chosen.metrics[k] ?? undefined, 2)}
                        </strong>
                        <em>{u}</em>
                      </div>
                    ))}
                  </div>
                )}
              </>
            )}
          </section>
        )}
        <footer>
          <span>
            HEATWIN <b> / </b> SOFTWARE-ONLY DIGITAL TWIN
          </span>
          <span>* Heat source is an imposed boundary · No boiler dynamics</span>
          <span>ENGINEERING EDUCATION / 2026</span>
        </footer>
        {error && (
          <div className="error" role="alert">
            {error} — start the Python API and retry.
          </div>
        )}
      </main>
    </div>
  );
}
function Reading({
  label,
  value,
  unit,
}: {
  label: string;
  value: string;
  unit: string;
}) {
  return (
    <div className="reading">
      <span>{label}</span>
      <strong>
        {value} <em>{unit}</em>
      </strong>
    </div>
  );
}
function NumberField({
  label,
  value,
  unit,
  step,
  onChange,
}: {
  label: string;
  value: number;
  unit: string;
  step: number;
  onChange: (v: number) => void;
}) {
  return (
    <div className="number-field">
      <label>{label}</label>
      <div>
        <input
          aria-label={label}
          type="number"
          value={value}
          step={step}
          onChange={(e) => onChange(Number(e.target.value))}
        />
        <small>{unit}</small>
        <ChevronDown size={11} />
      </div>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
