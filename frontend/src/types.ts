// API contract types mirroring the backend Pydantic schemas.

export interface Plant {
  id: number;
  name: string;
  country: string | null;
  region: string;
  frozen_weeks: number;
}

export interface ProductLine {
  id: number;
  plant_id: number;
  name: string;
  product_family: string | null;
  routing_info: string | null;
  sap_work_center: string | null;
  platforms: string[];
}

export interface CadenceOption {
  id: number;
  label: string;
  workers: number;
  shifts: number;
  pieces_per_week: number;
  active: boolean;
}

export interface CellComputed {
  expected_pieces: number;
  actual_output: number;
  frozen: boolean;
  has_note: boolean;
}

export interface Cell {
  product_line_id: number;
  iso_year_week: string;
  working_days: number;
  cadence_option_id: number | null;
  cadence_label: string | null;
  workers_assigned: number;
  capacity_delta: number;
  computed: CellComputed;
}

export interface GridRow {
  line: ProductLine;
  cells: Cell[];
}

export interface WorkforceStatus {
  iso_year_week: string;
  target_workers: number;
  assigned_workers: number;
  status: "above" | "at" | "below";
  delta: number;
}

export interface WeekTotals {
  iso_year_week: string;
  total_expected_pieces: number;
  total_actual_output: number;
  total_workers: number;
}

export interface GridResponse {
  plant: Plant;
  weeks: string[];
  rows: GridRow[];
  workforce: WorkforceStatus[];
  totals: WeekTotals[];
  // Configurable takt/cadence label (Column E); replaces the old hardcoded text.
  takt_label: string;
}

export interface CellUpdate {
  working_days?: number | null;
  cadence_option_id?: number | null;
  workers_assigned?: number | null;
  capacity_delta?: number | null;
}

export interface CurrentUser {
  id: number;
  username: string;
  display_name: string | null;
  role: "central-admin" | "planner" | "viewer" | "plant-viewer";
  scope_plant_id: number | null;
  scope_region: string | null;
}

export interface ApiError {
  error: { code: string; message: string; correlation_id: string };
}

// --- Versions (Official Version page) ------------------------------------

export interface Version {
  id: number;
  name: string;
  plant_id: number | null;
  kind: "named" | "official";
  explanation: string | null;
  created_by: string;
  created_at: string;
}

export interface SnapshotRow {
  product_line_id: number;
  line_name: string | null;
  iso_year_week: string;
  working_days: number;
  cadence_label: string | null;
  workers_assigned: number;
  capacity_delta: number;
  expected_pieces: number;
  actual_output: number;
}

export interface VersionSnapshotResponse {
  version_id: number;
  rows: SnapshotRow[];
  takt_label: string;
}

// --- Linked lines / Linee_Collegate --------------------------------------

export interface LineLink {
  id: number;
  plant_id: number;
  master_line_id: number;
  slave_line_id: number;
  master_line_name: string | null;
  slave_line_name: string | null;
  ratio: number;
}
