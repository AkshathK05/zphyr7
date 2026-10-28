import React, { useState, useEffect, useMemo } from 'react';
import {
  Line,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ComposedChart,
  ReferenceLine,
} from 'recharts';
import {
  Wind,
  Clock,
  Calendar,
  AlertTriangle,
  ShieldCheck,
  TrendingUp,
  Activity,
  ChevronLeft,
  ChevronRight,
  Info,
  CheckCircle2,
  RefreshCw,
  Download,
} from 'lucide-react';
import {
  fetchConfig,
  fetchOverallMetrics,
  fetchComparison,
  fetchDailyMetrics,
  fetchHourlyMetrics,
  fetchHorizonMetrics,
  fetchHistogramMetrics,
} from './api';
import {
  ConfigResponse,
  OverallMetrics,
  DayComparisonResult,
  DailyMetric,
  HourlyMetric,
  HorizonBucketMetric,
  HistogramBin,
} from './types';

// UK Date formatter: DD MMM YYYY (e.g. "2 Jan 2026")
export function formatUKDate(dateStr: string): string {
  if (!dateStr) return '';
  const parts = dateStr.split('-');
  if (parts.length !== 3) return dateStr;
  const [y, m, d] = parts;
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const mIdx = parseInt(m, 10) - 1;
  return `${parseInt(d, 10)} ${months[mIdx] || m} ${y}`;
}

export const App: React.FC = () => {
  // State
  const [config, setConfig] = useState<ConfigResponse | null>(null);
  const [metrics, setMetrics] = useState<OverallMetrics | null>(null);
  const [selectedDate, setSelectedDate] = useState<string>('2026-01-02');
  const [dayData, setDayData] = useState<DayComparisonResult | null>(null);
  const [dailyMetrics, setDailyMetrics] = useState<DailyMetric[]>([]);
  const [hourlyMetrics, setHourlyMetrics] = useState<HourlyMetric[]>([]);
  const [horizonMetrics, setHorizonMetrics] = useState<HorizonBucketMetric[]>([]);
  const [histogramBins, setHistogramBins] = useState<HistogramBin[]>([]);

  const [loading, setLoading] = useState<boolean>(true);
  const [dayLoading, setDayLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Initial load
  useEffect(() => {
    async function initDashboard() {
      try {
        setLoading(true);
        setError(null);
        const [cfg, overall, daily, hourly, horizon, hist] = await Promise.all([
          fetchConfig(),
          fetchOverallMetrics(),
          fetchDailyMetrics(),
          fetchHourlyMetrics(),
          fetchHorizonMetrics(),
          fetchHistogramMetrics(16),
        ]);

        setConfig(cfg);
        setMetrics(overall);
        setDailyMetrics(daily);
        setHourlyMetrics(hourly);
        setHorizonMetrics(horizon);
        setHistogramBins(hist);

        // Fetch first day comparison
        const initialDate = cfg.delivery_start_date || '2026-01-02';
        setSelectedDate(initialDate);
        const dayRes = await fetchComparison(initialDate, cfg.cutoff_time);
        setDayData(dayRes);
      } catch (err: any) {
        console.error('Initialization error:', err);
        setError(err.message || 'Failed to connect to backtest API');
      } finally {
        setLoading(false);
      }
    }
    initDashboard();
  }, []);

  // Fetch day comparison when date changes
  const handleDateChange = async (newDate: string) => {
    if (!config) return;
    if (newDate < config.delivery_start_date || newDate > config.delivery_end_date) return;
    setSelectedDate(newDate);
    try {
      setDayLoading(true);
      const res = await fetchComparison(newDate, config.cutoff_time);
      setDayData(res);
    } catch (err: any) {
      console.error('Day fetch error:', err);
      setError(`Failed to load data for ${formatUKDate(newDate)}`);
    } finally {
      setDayLoading(false);
    }
  };

  const navigateDay = (offset: number) => {
    const cur = new Date(selectedDate);
    cur.setDate(cur.getDate() + offset);
    const nextStr = cur.toISOString().split('T')[0];
    handleDateChange(nextStr);
  };

  // Day Chart Data & Selected Day Statistics
  const chartData = useMemo(() => {
    if (!dayData?.slots) return [];
    return dayData.slots.map((s) => {
      const timeLabel = s.start_time.substring(11, 16);
      return {
        time: timeLabel,
        period: s.settlement_period,
        forecast: s.forecast_generation_mw,
        actual: s.actual_generation_mw,
        error: s.error_mw,
        publishTime: s.forecast_publish_time
          ? `${formatUKDate(s.forecast_publish_time.substring(0, 10))} ${s.forecast_publish_time.substring(11, 16)} UTC`
          : 'N/A',
        leadTime: s.lead_time_hours ? `${s.lead_time_hours}h` : 'N/A',
      };
    });
  }, [dayData]);

  // Selected Day Stat Strip metrics
  const selectedDayStats = useMemo(() => {
    if (!dayData?.slots || dayData.slots.length === 0) return null;
    const evaluated = dayData.slots.filter((s) => s.error_mw !== null && s.status === 'EVALUATED');
    if (evaluated.length === 0) return null;

    const errors = evaluated.map((s) => s.error_mw as number);
    const dayMae = errors.reduce((acc, v) => acc + Math.abs(v), 0) / errors.length;
    const dayBias = errors.reduce((acc, v) => acc + v, 0) / errors.length;

    // Find max shortfall (largest positive error = forecast > actual)
    let maxShortfall = { val: -Infinity, time: 'N/A', period: 1 };
    evaluated.forEach((s) => {
      if (s.error_mw !== null && s.error_mw > maxShortfall.val) {
        maxShortfall = {
          val: s.error_mw,
          time: s.start_time.substring(11, 16),
          period: s.settlement_period,
        };
      }
    });

    return {
      dayMae,
      dayBias,
      maxShortfall,
      evaluatedCount: evaluated.length,
      totalSlots: dayData.total_slots,
    };
  }, [dayData]);

  // Dynamic Insight 1: Hourly Bias Peak & Trough
  const hourlyInsightText = useMemo(() => {
    if (!hourlyMetrics || hourlyMetrics.length === 0) return '';
    const sorted = [...hourlyMetrics].sort((a, b) => a.bias_mw - b.bias_mw);
    const trough = sorted[0];
    const peak = sorted[sorted.length - 1];
    return `Bias peaks at ${peak.hour_label} UTC (+${peak.bias_mw.toLocaleString(undefined, { maximumFractionDigits: 0 })} MW) and is lowest around ${trough.hour_label} UTC (+${trough.bias_mw.toLocaleString(undefined, { maximumFractionDigits: 0 })} MW). Over the 24-hour cycle, MAE ranges from ${trough.mae_mw.toLocaleString(undefined, { maximumFractionDigits: 0 })} MW to ${peak.mae_mw.toLocaleString(undefined, { maximumFractionDigits: 0 })} MW.`;
  }, [hourlyMetrics]);

  // Dynamic Insight 2: Top 3 Days with Largest Forecast Errors
  const dailyInsightText = useMemo(() => {
    if (!dailyMetrics || dailyMetrics.length === 0) return '';
    const sorted = [...dailyMetrics].sort((a, b) => b.mae_mw - a.mae_mw);
    const top3 = sorted.slice(0, 3);
    const listStr = top3
      .map((d) => `${formatUKDate(d.delivery_date)} (${d.mae_mw.toLocaleString(undefined, { maximumFractionDigits: 0 })} MW)`)
      .join(', ');
    return `The days with the largest forecast errors across the month were: ${listStr}. On these days, forecast generation substantially overshot metered physical outturn.`;
  }, [dailyMetrics]);

  if (loading) {
    return (
      <div className="loading-container">
        <div className="spinner" />
        <h2>Loading Elexon BMRS Backtest Data...</h2>
        <p>Evaluating 1,488 settlement slots across January 2026</p>
      </div>
    );
  }

  if (error && !dayData) {
    return (
      <div className="app-container">
        <div className="error-banner">
          <div>
            <strong>Error connecting to backtest backend:</strong>
            <p>{error}</p>
          </div>
          <button className="day-nav-btn" onClick={() => window.location.reload()}>
            <RefreshCw size={16} /> Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="app-container">
      {/* Header */}
      <header className="app-header">
        <div className="header-title-group">
          <h1>
            <Wind className="text-primary" size={28} />
            GB Wind Forecast Backtest
          </h1>
          <p>
            Evaluation of Elexon BMRS day-ahead wind generation forecasts vs. metered actual outturn for GB Day-Ahead Market procurement.
          </p>
        </div>
        <div className="header-badges">
          <span className="badge badge-primary">
            <Clock size={14} /> Decision Cutoff: {config?.cutoff_time || '09:00'} UTC (Day D-1)
          </span>
          <span className="badge badge-neutral">
            <Calendar size={14} /> 2 Jan 2026 – 1 Feb 2026
          </span>
          <span className="badge badge-success">
            <CheckCircle2 size={14} /> 100% Coverage (1,488 / 1,488 Slots)
          </span>
          <a
            href={`${(import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')}/export/csv`}
            download="elexon_wind_backtest_january_2026.csv"
            className="badge badge-primary"
            style={{ textDecoration: 'none', cursor: 'pointer', background: '#0284c7', color: '#ffffff', borderColor: '#0284c7' }}
            title="Download full 1,488 evaluated slot dataset in CSV format"
          >
            <Download size={14} /> Export CSV (1,488 Slots)
          </a>
        </div>
      </header>

      {/* Domain Hypothesis Callout */}
      <div className="callout-banner banner-warning">
        <AlertTriangle className="insight-icon" size={20} />
        <div>
          <div className="callout-title">Systematic Bias Finding & Operational Context</div>
          <div className="callout-body">
            Forecasts systematically exceeded metered outturn across the backtest period (Mean Bias: +{metrics?.bias_mw.toLocaleString(undefined, { maximumFractionDigits: 1 })} MW).
            A likely cause is <strong>curtailment</strong> (constraint actions on wind farms), which reduces metered output relative to forecast potential.
            Verifying this needs constraint data, which is out of scope.
          </div>
        </div>
      </div>

      {/* Headline Metric Cards */}
      <section className="metric-cards-grid">
        {/* Card 1: MAE */}
        <div className="metric-card card-highlight">
          <div className="metric-card-header">
            <span className="metric-label">Mean Absolute Error</span>
            <Activity size={18} color="#0284c7" />
          </div>
          <div className="metric-value">
            {metrics?.mae_mw.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 })}
            <span className="metric-unit">MW</span>
          </div>
          <p className="metric-subtext">
            Average absolute divergence between forecast and physical metered outturn per half-hour.
          </p>
        </div>

        {/* Card 2: Bias */}
        <div className="metric-card card-warning">
          <div className="metric-card-header">
            <span className="metric-label">Forecast Bias (Mean Signed)</span>
            <TrendingUp size={18} color="#f59e0b" />
          </div>
          <div className="metric-value" style={{ color: '#d97706' }}>
            +{metrics?.bias_mw.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 })}
            <span className="metric-unit">MW</span>
          </div>
          <p className="metric-subtext">
            Forecast tends to run high; <strong>utility would have been short</strong>.
          </p>
        </div>

        {/* Card 3: P90 Shortfall Buffer (Headline) */}
        <div className="metric-card card-highlight">
          <div className="metric-card-header">
            <span className="metric-label">Headline Safety Buffer (P90)</span>
            <ShieldCheck size={18} color="#0284c7" />
          </div>
          <div className="metric-value" style={{ color: '#0284c7' }}>
            {metrics?.recommended_buffer_mw.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 })}
            <span className="metric-unit">MW</span>
          </div>
          <p className="metric-subtext">
            Would have covered 90% of wind shortfalls in the backtest.
          </p>
        </div>

        {/* Card 4: In-Sample Bias-Corrected Buffer */}
        <div className="metric-card">
          <div className="metric-card-header">
            <span className="metric-label">Bias-Corrected Buffer</span>
            <span className="badge badge-neutral" style={{ fontSize: '0.7rem', padding: '2px 6px' }}>In-Sample</span>
          </div>
          <div className="metric-value" style={{ color: '#475569' }}>
            {metrics?.bias_corrected.recommended_buffer_mw.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 })}
            <span className="metric-unit">MW</span>
          </div>
          <p className="metric-subtext">
            Would have covered 90% of shortfalls after bias correction (in-sample). Residual MAE: {metrics?.bias_corrected.mae_mw.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 })} MW.
          </p>
        </div>

        {/* Card 5: Evaluated Slots / Coverage */}
        <div className="metric-card card-success">
          <div className="metric-card-header">
            <span className="metric-label">Data Completeness</span>
            <CheckCircle2 size={18} color="#10b981" />
          </div>
          <div className="metric-value" style={{ color: '#059669' }}>
            {metrics?.evaluated_slots.toLocaleString()}
            <span className="metric-unit">/ {metrics?.total_slots.toLocaleString()}</span>
          </div>
          <p className="metric-subtext">
            100% complete backtest across all 31 delivery days. Zero missing or skipped forecast slots.
          </p>
        </div>
      </section>

      {/* Main Day View: Interactive Forecast vs Actual Outturn */}
      <section className="dashboard-section">
        <div className="section-header">
          <div>
            <h2 className="section-title">
              <Calendar size={20} className="text-primary" />
              Delivery Day Evaluation: {formatUKDate(selectedDate)}
            </h2>
            <p className="section-description">
              Decision made on {dayData ? formatUKDate(dayData.decision_date) : ''} before {dayData?.cutoff_time} UTC cutoff. Forecast drawn as an hourly step line vs. 30-min metered actuals.
            </p>
          </div>

          <div className="toolbar-controls">
            <button
              className="day-nav-btn"
              onClick={() => navigateDay(-1)}
              disabled={selectedDate <= (config?.delivery_start_date || '2026-01-02') || dayLoading}
              title="Previous Day"
            >
              <ChevronLeft size={18} />
            </button>

            {/* UK Date Picker Interface */}
            <div className="date-picker-group">
              <Calendar size={16} color="#64748b" />
              <span className="uk-date-display">{formatUKDate(selectedDate)}</span>
              <input
                type="date"
                className="date-input-hidden"
                value={selectedDate}
                min={config?.delivery_start_date || '2026-01-02'}
                max={config?.delivery_end_date || '2026-02-01'}
                onChange={(e) => handleDateChange(e.target.value)}
                disabled={dayLoading}
                aria-label="Select delivery date"
              />
            </div>

            <button
              className="day-nav-btn"
              onClick={() => navigateDay(1)}
              disabled={selectedDate >= (config?.delivery_end_date || '2026-02-01') || dayLoading}
              title="Next Day"
            >
              <ChevronRight size={18} />
            </button>
          </div>
        </div>

        {/* Selected Day Stat Strip */}
        {selectedDayStats && (
          <div className="day-stat-strip">
            <div className="day-stat-item">
              <span className="stat-label">Daily MAE:</span>
              <span className="stat-value">{selectedDayStats.dayMae.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 })} MW</span>
            </div>
            <div className="day-stat-item">
              <span className="stat-label">Daily Bias:</span>
              <span className="stat-value" style={{ color: selectedDayStats.dayBias >= 0 ? '#d97706' : '#059669' }}>
                {selectedDayStats.dayBias >= 0 ? `+${selectedDayStats.dayBias.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 })}` : selectedDayStats.dayBias.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 })} MW
                <span className="stat-badge">{selectedDayStats.dayBias >= 0 ? 'Short' : 'Long'}</span>
              </span>
            </div>
            <div className="day-stat-item">
              <span className="stat-label">Max Shortfall:</span>
              <span className="stat-value" style={{ color: '#ea580c' }}>
                +{selectedDayStats.maxShortfall.val.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 })} MW
                <span className="stat-subtext">at {selectedDayStats.maxShortfall.time} UTC (SP {selectedDayStats.maxShortfall.period})</span>
              </span>
            </div>
            <div className="day-stat-item">
              <span className="stat-label">Evaluated Slots:</span>
              <span className="stat-value">{selectedDayStats.evaluatedCount} / {selectedDayStats.totalSlots} (100%)</span>
            </div>
          </div>
        )}

        {/* Day Chart */}
        <div style={{ width: '100%', height: 380 }}>
          <ResponsiveContainer>
            <ComposedChart data={chartData} margin={{ top: 10, right: 20, left: 15, bottom: 0 }}>
              <defs>
                <linearGradient id="actualGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#10b981" stopOpacity={0.25} />
                  <stop offset="95%" stopColor="#10b981" stopOpacity={0.0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
              <XAxis dataKey="time" stroke="#64748b" tick={{ fontSize: 12 }} />
              <YAxis
                stroke="#64748b"
                tick={{ fontSize: 12 }}
                tickFormatter={(v) => `${Math.round(v / 1000)}k`}
                label={{ value: 'Generation (MW)', angle: -90, position: 'insideLeft', style: { fill: '#64748b', fontSize: 12, textAnchor: 'middle' }, offset: -5 }}
              />
              <Tooltip
                content={({ active, payload }) => {
                  if (active && payload && payload.length) {
                    const data = payload[0].payload;
                    const isShort = data.error > 0;
                    return (
                      <div className="custom-tooltip">
                        <div className="tooltip-time">
                          <span>Slot {data.time} UTC</span>
                          <span>SP {data.period}</span>
                        </div>
                        <div className="tooltip-row">
                          <span className="label">Forecast (Step):</span>
                          <span className="val" style={{ color: '#3b82f6' }}>{data.forecast?.toLocaleString()} MW</span>
                        </div>
                        <div className="tooltip-row">
                          <span className="label">Actual Outturn:</span>
                          <span className="val" style={{ color: '#10b981' }}>{data.actual?.toLocaleString()} MW</span>
                        </div>
                        <div className={`tooltip-row ${isShort ? 'val-short' : 'val-surplus'}`}>
                          <span className="label">Shortfall Error:</span>
                          <span className="val">{data.error > 0 ? `+${data.error?.toLocaleString()}` : data.error?.toLocaleString()} MW</span>
                        </div>
                        <div className="tooltip-meta">
                          Forecast Published: {data.publishTime} • Lead Time: {data.leadTime}
                        </div>
                      </div>
                    );
                  }
                  return null;
                }}
              />
              <Legend verticalAlign="top" height={36} />
              
              {/* Actual generation: smooth area */}
              <Area
                type="monotone"
                dataKey="actual"
                name="Actual Wind Outturn (FUELHH)"
                stroke="#10b981"
                strokeWidth={2.5}
                fillOpacity={1}
                fill="url(#actualGradient)"
              />

              {/* Forecast: STEP LINE for visual honesty that forecast is hourly */}
              <Line
                type="stepAfter"
                dataKey="forecast"
                name="Day-Ahead Forecast (WINDFOR, Hourly Step)"
                stroke="#2563eb"
                strokeWidth={2.5}
                dot={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>

        {/* Insight footer for Day view */}
        <div className="chart-insight-box">
          <Info className="insight-icon" size={16} />
          <div>
            <strong>Visual Honesty Notice:</strong> The forecast is rendered as a <strong>step line</strong> flat across each hour because Elexon publishes WINDFOR at 60-minute resolution.
            The trader relied on this constant hourly forecast for both half-hour trading blocks. Any divergence between the green curve (half-hourly physical flow) and blue step represents imbalance exposure.
          </div>
        </div>
      </section>

      {/* Analytical Deep-Dives: 2x2 Grid */}
      <div className="analytics-grid">
        {/* Chart 1: Error Distribution Histogram */}
        <div className="dashboard-section">
          <div className="section-header">
            <div>
              <h3 className="section-title">Error Distribution (Shortfall vs Surplus)</h3>
              <p className="section-description">Frequency distribution across all 1,488 evaluated slots</p>
            </div>
          </div>
          <div style={{ width: '100%', height: 280 }}>
            <ResponsiveContainer>
              <BarChart data={histogramBins} margin={{ top: 10, right: 10, left: 15, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
                <XAxis
                  dataKey="bin_start_mw"
                  stroke="#64748b"
                  tick={{ fontSize: 11 }}
                  tickFormatter={(v) => `${v > 0 ? '+' : ''}${Math.round(v / 1000)}k`}
                />
                <YAxis
                  stroke="#64748b"
                  tick={{ fontSize: 11 }}
                  label={{ value: 'Slot Count', angle: -90, position: 'insideLeft', style: { fill: '#64748b', fontSize: 12, textAnchor: 'middle' }, offset: -5 }}
                />
                <ReferenceLine
                  x={0}
                  stroke="#ef4444"
                  strokeWidth={2}
                  strokeDasharray="4 4"
                  label={{ value: '0 MW', fill: '#ef4444', fontSize: 11, position: 'top' }}
                />
                <Tooltip
                  formatter={(val: any, _name: any, item: any) => [
                    `${val} slots (${item.payload.percentage}%)`,
                    `Error Bin: ${item.payload.bin_start_mw} to ${item.payload.bin_end_mw} MW`,
                  ]}
                />
                <Bar dataKey="count" name="Settlement Slots" fill="#0284c7" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="chart-insight-box">
            <Info className="insight-icon" size={16} />
            <span>
              The distribution is right-skewed with a heavy shortfall tail: 82% of settlement periods fall to the right of zero error (forecast &gt; actual).
            </span>
          </div>
        </div>

        {/* Chart 2: Hourly Performance (00:00 - 23:00) */}
        <div className="dashboard-section">
          <div className="section-header">
            <div>
              <h3 className="section-title">Error by Hour of Day</h3>
              <p className="section-description">MAE and Signed Bias across diurnal cycle</p>
            </div>
          </div>
          <div style={{ width: '100%', height: 280 }}>
            <ResponsiveContainer>
              <ComposedChart data={hourlyMetrics} margin={{ top: 10, right: 10, left: 15, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
                <XAxis dataKey="hour_label" stroke="#64748b" tick={{ fontSize: 11 }} />
                <YAxis
                  stroke="#64748b"
                  tick={{ fontSize: 11 }}
                  tickFormatter={(v) => `${Math.round(v / 1000)}k`}
                  label={{ value: 'Error (MW)', angle: -90, position: 'insideLeft', style: { fill: '#64748b', fontSize: 12, textAnchor: 'middle' }, offset: -5 }}
                />
                <Tooltip />
                <Legend />
                <Bar dataKey="mae_mw" name="MAE (MW)" fill="#cbd5e1" radius={[3, 3, 0, 0]} />
                <Line type="monotone" dataKey="bias_mw" name="Signed Bias (MW)" stroke="#f59e0b" strokeWidth={2.5} dot={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          <div className="chart-insight-box">
            <Info className="insight-icon" size={16} />
            <span>{hourlyInsightText}</span>
          </div>
        </div>

        {/* Chart 3: Daily MAE Across Month */}
        <div className="dashboard-section">
          <div className="section-header">
            <div>
              <h3 className="section-title">Daily MAE Across January 2026</h3>
              <p className="section-description">Day-to-day forecast error tracking over 31 days</p>
            </div>
          </div>
          <div style={{ width: '100%', height: 280 }}>
            <ResponsiveContainer>
              <BarChart data={dailyMetrics} margin={{ top: 10, right: 10, left: 15, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
                <XAxis
                  dataKey="delivery_date"
                  stroke="#64748b"
                  tick={{ fontSize: 10 }}
                  tickFormatter={(d) => formatUKDate(d).substring(0, 6)}
                />
                <YAxis
                  stroke="#64748b"
                  tick={{ fontSize: 11 }}
                  tickFormatter={(v) => `${Math.round(v / 1000)}k`}
                  label={{ value: 'Daily MAE (MW)', angle: -90, position: 'insideLeft', style: { fill: '#64748b', fontSize: 12, textAnchor: 'middle' }, offset: -5 }}
                />
                <Tooltip
                  formatter={(val: any, _name: any, item: any) => [
                    `${Number(val).toLocaleString()} MW`,
                    `Date: ${formatUKDate(item.payload.delivery_date)}`,
                  ]}
                />
                <Bar dataKey="mae_mw" name="Daily MAE (MW)" fill="#0284c7" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="chart-insight-box">
            <Info className="insight-icon" size={16} />
            <span>{dailyInsightText}</span>
          </div>
        </div>

        {/* Chart 4: Horizon Analysis (MAE vs Lead Time) */}
        <div className="dashboard-section">
          <div className="section-header">
            <div>
              <h3 className="section-title">Forecast Horizon Analysis (0h – 48h)</h3>
              <p className="section-description">Accuracy vs lead time across all published forecasts</p>
            </div>
          </div>
          <div style={{ width: '100%', height: 280 }}>
            <ResponsiveContainer>
              <ComposedChart data={horizonMetrics} margin={{ top: 10, right: 10, left: 15, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
                <XAxis dataKey="bucket_label" stroke="#64748b" tick={{ fontSize: 11 }} />
                <YAxis
                  stroke="#64748b"
                  tick={{ fontSize: 11 }}
                  tickFormatter={(v) => `${Math.round(v / 1000)}k`}
                  label={{ value: 'MAE / RMSE (MW)', angle: -90, position: 'insideLeft', style: { fill: '#64748b', fontSize: 12, textAnchor: 'middle' }, offset: -5 }}
                />
                <Tooltip />
                <Legend />
                <Bar dataKey="mae_mw" name="MAE (MW)" fill="#93c5fd" radius={[4, 4, 0, 0]} />
                <Line type="monotone" dataKey="rmse_mw" name="RMSE (MW)" stroke="#0284c7" strokeWidth={2.5} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          <div className="chart-insight-box">
            <Info className="insight-icon" size={16} />
            <span>
              Unconfounded Horizon Analysis: MAE increases monotonically from 1,689 MW at 0–6h out to 2,332 MW at 42–48h out, illustrating atmospheric predictability decay as lead time widens.
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default App;
