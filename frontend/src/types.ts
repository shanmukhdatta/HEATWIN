export type Sample = {
  time: number;
  tc: number;
  th: number;
  valve: number;
  setpoint: number;
  measurement: number;
  command: number;
  tc_in: number;
  ua: number;
  mc: number;
  fault_active: boolean;
  twin: number;
  residual: number;
  alarm: boolean;
  hot_flow: number;
  heat_w: number;
};
export type Run = {
  samples: Sample[];
  metrics: Record<string, number | null>;
  gains: number[];
};
export type Result = {
  runs: Record<string, Run>;
  model: number[];
  hot_inlet: number;
  sample_time: number;
  seed: number;
};
export type Config = {
  duration: number;
  setpoint: number;
  kp: number;
  ki: number;
  kd: number;
  ua: number;
  controller: string;
  tuning: string;
  mode: string;
  manual_valve: number;
  compare: boolean;
  fault: string;
  fault_time: number;
  seed: number;
  initial_state: [number, number, number] | null;
};
export const defaults: Config = {
  duration: 360,
  setpoint: 57,
  kp: 0.04,
  ki: 0.001,
  kd: 0.08,
  ua: 350,
  controller: "PID",
  tuning: "manual",
  mode: "auto",
  manual_valve: 0.4,
  compare: false,
  fault: "none",
  fault_time: 120,
  seed: 42,
  initial_state: null,
};
export function indexAt(time: number, length: number) {
  return Math.min(Math.max(Math.floor(time), 0), Math.max(length - 1, 0));
}
export function display(value: number | undefined, digits = 1) {
  return value === undefined || !Number.isFinite(value)
    ? "—"
    : value.toFixed(digits);
}
