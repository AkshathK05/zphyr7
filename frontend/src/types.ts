export interface SlotComparison {
  start_time: string;
  settlement_date: string;
  settlement_period: number;
  forecast_generation_mw: number | null;
  actual_generation_mw: number | null;
  error_mw: number | null;
  forecast_publish_time: string | null;
  actual_publish_time: string | null;
  lead_time_hours: number | null;
  status: 'EVALUATED' | 'SKIPPED';
  skip_reason?: string | null;
}

export interface DayComparisonResult {
  delivery_date: string;
  decision_date: string;
  cutoff_time: string;
  cutoff_timestamp: string;
  total_slots: number;
  evaluated_slots: number;
  skipped_slots: number;
  slots: SlotComparison[];
}

export interface BiasCorrectedMetrics {
  mean_bias_subtracted_mw: number;
  mae_mw: number;
  p10_mw: number;
  p50_mw: number;
  p90_mw: number;
  recommended_buffer_mw: number;
  explanation: string;
}

export interface OverallMetrics {
  total_slots: number;
  evaluated_slots: number;
  skipped_slots: number;
  coverage_pct: number;
  mae_mw: number;
  bias_mw: number;
  rmse_mw: number;
  p10_mw: number;
  p50_mw: number;
  p90_mw: number;
  min_error_mw: number;
  max_error_mw: number;
  std_error_mw: number;
  recommended_buffer_mw: number;
  headline_explanation: string;
  bias_corrected: BiasCorrectedMetrics;
}

export interface DailyMetric {
  delivery_date: string;
  decision_date: string;
  cutoff_time: string;
  evaluated_slots: number;
  skipped_slots: number;
  mae_mw: number;
  bias_mw: number;
  rmse_mw: number;
  p10_mw: number;
  p50_mw: number;
  p90_mw: number;
  max_shortfall_mw: number;
}

export interface HourlyMetric {
  hour: number;
  hour_label: string;
  evaluated_slots: number;
  mae_mw: number;
  bias_mw: number;
  rmse_mw: number;
  p10_mw: number;
  p50_mw: number;
  p90_mw: number;
  avg_forecast_mw: number;
  avg_actual_mw: number;
}

export interface HorizonBucketMetric {
  bucket_label: string;
  min_hours: number;
  max_hours: number;
  forecast_count: number;
  mae_mw: number;
  bias_mw: number;
  rmse_mw: number;
}

export interface HistogramBin {
  bin_start_mw: number;
  bin_end_mw: number;
  count: number;
  percentage: number;
}

export interface ConfigResponse {
  elexon_base_url: string;
  cutoff_time: string;
  decision_start_date: string;
  decision_end_date: string;
  delivery_start_date: string;
  delivery_end_date: string;
  resolution_alignment: string;
}
