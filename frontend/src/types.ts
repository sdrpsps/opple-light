export interface LightState {
  power: boolean;
  color_temperature_kelvin: number;
  brightness_percent: number;
}
export type StatePatch = Partial<LightState>;
export interface Timer {
  id: string;
  light_id: string;
  due_at: number;
  minutes: number;
  status: 'active' | 'executing' | 'completed' | 'failed' | 'expired' | 'cancelled';
  message?: string;
}
export interface Light {
  id: string;
  name: string;
  host: string;
  online: boolean;
  state: LightState | null;
  pending_settings: StatePatch;
  capabilities: { min_kelvin: number; max_kelvin: number };
  last_seen: string | null;
  error?: string;
  timer: Timer | null;
}
export interface Snapshot {
  name: string;
  version: string;
  server_time: number;
  timezone: string;
  lights: Light[];
}
export type SceneIcon = 'sun' | 'book' | 'moon' | 'spark';
export interface SceneBody {
  name: string;
  color_temperature_kelvin: number;
  brightness_percent: number;
  icon: SceneIcon;
}
export interface Scene extends SceneBody {
  id: string;
  light_id: string;
}
export interface Operation {
  id: string;
  status:
    | 'pending'
    | 'running'
    | 'confirmed'
    | 'staged'
    | 'failed'
    | 'expired'
    | 'cancelled'
    | 'superseded';
  message: string;
}
export interface Session {
  authenticated: boolean;
  login_enabled?: boolean;
  name?: string;
}
export interface LightEvent {
  id?: string;
  at: string;
  kind: string;
  message: string;
}
