import {
  ConfigResponse,
  OverallMetrics,
  DayComparisonResult,
  DailyMetric,
  HourlyMetric,
  HorizonBucketMetric,
  HistogramBin,
} from './types';

const BASE_URL = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '');

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`API Error ${res.status}: ${errorText || res.statusText}`);
  }
  return res.json();
}

export async function fetchConfig(): Promise<ConfigResponse> {
  const res = await fetch(`${BASE_URL}/config`);
  return handleResponse<ConfigResponse>(res);
}

export async function fetchOverallMetrics(cutoff?: string): Promise<OverallMetrics> {
  const url = cutoff ? `${BASE_URL}/metrics?cutoff=${encodeURIComponent(cutoff)}` : `${BASE_URL}/metrics`;
  const res = await fetch(url);
  return handleResponse<OverallMetrics>(res);
}

export async function fetchComparison(date: string, cutoff?: string): Promise<DayComparisonResult> {
  let url = `${BASE_URL}/comparison?date=${encodeURIComponent(date)}`;
  if (cutoff) {
    url += `&cutoff=${encodeURIComponent(cutoff)}`;
  }
  const res = await fetch(url);
  return handleResponse<DayComparisonResult>(res);
}

export async function fetchDailyMetrics(cutoff?: string): Promise<DailyMetric[]> {
  const url = cutoff ? `${BASE_URL}/metrics/daily?cutoff=${encodeURIComponent(cutoff)}` : `${BASE_URL}/metrics/daily`;
  const res = await fetch(url);
  return handleResponse<DailyMetric[]>(res);
}

export async function fetchHourlyMetrics(cutoff?: string): Promise<HourlyMetric[]> {
  const url = cutoff ? `${BASE_URL}/metrics/by-hour?cutoff=${encodeURIComponent(cutoff)}` : `${BASE_URL}/metrics/by-hour`;
  const res = await fetch(url);
  return handleResponse<HourlyMetric[]>(res);
}

export async function fetchHorizonMetrics(): Promise<HorizonBucketMetric[]> {
  const res = await fetch(`${BASE_URL}/metrics/horizon`);
  return handleResponse<HorizonBucketMetric[]>(res);
}

export async function fetchHistogramMetrics(bins: number = 16): Promise<HistogramBin[]> {
  const res = await fetch(`${BASE_URL}/metrics/histogram?bins=${bins}`);
  return handleResponse<HistogramBin[]>(res);
}
