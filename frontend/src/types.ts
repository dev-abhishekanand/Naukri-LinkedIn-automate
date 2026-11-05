export interface PowerStatus {
  is_on_battery?: boolean;
  power_source?: string;
  battery_percent?: number;
  time_remaining?: string;
  should_throttle?: boolean;
}

export interface OperationalWindow {
  is_silent?: boolean;
  label?: string;
  desc?: string;
}

export interface SessionsMap {
  naukri_primary?: boolean;
  naukri_secondary?: boolean;
  linkedin?: boolean;
  indeed?: boolean;
  instahyre?: boolean;
  cutshort?: boolean;
  wellfound?: boolean;
  hirist?: boolean;
  universal_ats?: boolean;
}

export interface CandidateProfile {
  name: string;
  email: string;
  phone: string;
  experience: number;
  notice_period: string;
  target_roles: string[];
  current_city: string;
}

export interface StatusData {
  candidate?: CandidateProfile;
  sessions?: SessionsMap;
  power_status?: PowerStatus;
  operational_window?: OperationalWindow;
  metrics?: any;
  all_metrics?: any;
  recent_applications?: any[];
}

export interface RunStatus {
  is_running: boolean;
  task_name?: string;
  logs: string[];
  total_log_lines?: number;
}
