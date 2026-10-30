"use client";

import React, { useState, useEffect } from "react";
import {
  Sun,
  Wind,
  Waves,
  Zap,
  TrendingDown,
  ShieldAlert,
  BarChart3,
  Calendar,
  Layers,
  Sparkles,
  HelpCircle,
  Activity,
  ArrowRight,
  Database,
  RefreshCw,
} from "lucide-react";

interface PricingResponse {
  asset_name: string;
  technology: string;
  capacity_mw: number;
  tenor_years: number;
  fair_ppa_fixed_price: number;
  expected_baseload_price: number;
  cannibalization_discount: number;
  expected_capture_price: number;
  balancing_cost: number;
  risk_premium: number;
  floor_option_value: number;
  capture_factor_expected: number;
  expected_annual_generation_mwh: number;
  expected_annual_revenue_ppa_eur: number;
  expected_annual_revenue_merchant_eur: number;
  waterfall: Record<string, number>;
  summary_table: Record<string, any>;
  risk_metrics: Record<string, any>;
}

interface DuckCurvePoint {
  hour_of_day_utc: number;
  avg_price_eur_mwh: number;
  avg_solar_mwh: number;
  avg_wind_onshore_mwh: number;
  negative_price_occurrences: number;
}

const API_BASE = (
  process.env.NEXT_PUBLIC_API_URL || "https://ppa-pricing-and-risk-tool-for-a-german.onrender.com"
).replace(/\/$/, "");

export default function PpaPricingTerminal() {
  // Console Inputs
  const [tech, setTech] = useState<string>("solar_pv");
  const [capacity, setCapacity] = useState<number>(50.0);
  const [location, setLocation] = useState<string>("bavaria_solar");
  const [tenor, setTenor] = useState<number>(5);
  const [baseload, setBaseload] = useState<number>(65.0);
  const [balancingCost, setBalancingCost] = useState<number>(2.5);
  const [riskMargin, setRiskMargin] = useState<number>(1.5);
  const [enableFloor, setEnableFloor] = useState<boolean>(false);
  const [floorPrice, setFloorPrice] = useState<number>(0.0);
  const [scenarios, setScenarios] = useState<number>(500);

  // States
  const [loading, setLoading] = useState<boolean>(false);
  const [result, setResult] = useState<PricingResponse | null>(null);
  const [duckCurve, setDuckCurve] = useState<DuckCurvePoint[]>([]);
  const [activeTab, setActiveTab] = useState<"waterfall" | "fanchart" | "duckcurve" | "negative" | "audit">("waterfall");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Fetch initial valuation & duck curve
  useEffect(() => {
    runValuation();
    fetchDuckCurve();
  }, []);

  const runValuation = async () => {
    setLoading(true);
    setErrorMsg(null);
    try {
      const res = await fetch(`${API_BASE}/api/price`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          technology: tech,
          capacity_mw: Number(capacity),
          location_id: location,
          tenor_years: Number(tenor),
          expected_baseload_eur_mwh: Number(baseload),
          balancing_cost_eur_mwh: Number(balancingCost),
          risk_premium_eur_mwh: Number(riskMargin),
          floor_price_eur_mwh: enableFloor ? Number(floorPrice) : null,
          num_scenarios: Number(scenarios),
        }),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Pricing calculation failed");
      }

      const data: PricingResponse = await res.json();
      setResult(data);
    } catch (err: any) {
      console.error(err);
      setErrorMsg(err.message || "Failed to connect to FastAPI backend");
    } finally {
      setLoading(false);
    }
  };

  const fetchDuckCurve = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/duck-curve`);
      if (res.ok) {
        const data = await res.json();
        setDuckCurve(data);
      }
    } catch (e) {
      console.error("Failed to fetch duck curve", e);
    }
  };

  // Location selector presets by tech
  const locationsByTech: Record<string, { id: string; label: string }[]> = {
    solar_pv: [
      { id: "bavaria_solar", label: "Bavaria (High Irradiance Hub)" },
      { id: "brandenburg_solar", label: "Brandenburg (Eastern Solar Belt)" },
    ],
    wind_onshore: [
      { id: "lower_saxony_wind", label: "Lower Saxony (High-Yield Onshore)" },
      { id: "schleswig_wind", label: "Schleswig-Holstein (Coastal Corridor)" },
    ],
    wind_offshore: [
      { id: "north_sea_offshore", label: "North Sea (German Bight Cluster)" },
    ],
  };

  const handleTechChange = (newTech: string) => {
    setTech(newTech);
    const available = locationsByTech[newTech];
    if (available && available.length > 0) {
      setLocation(available[0].id);
    }
  };

  return (
    <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column" }}>
      {/* Top Navigation Bar */}
      <header
        style={{
          height: "64px",
          borderBottom: "1px solid var(--border-subtle)",
          background: "rgba(10, 14, 23, 0.85)",
          backdropFilter: "blur(12px)",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "0 28px",
          position: "sticky",
          top: 0,
          zIndex: 50,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "14px" }}>
          <div
            style={{
              width: "38px",
              height: "38px",
              borderRadius: "10px",
              background: "linear-gradient(135deg, #00f5a0 0%, #00d9f5 100%)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              boxShadow: "0 0 16px rgba(0, 245, 160, 0.4)",
            }}
          >
            <Zap size={22} color="#07090e" strokeWidth={2.5} />
          </div>
          <div>
            <div style={{ fontWeight: 800, fontSize: "1.05rem", letterSpacing: "0.02em" }}>
              GERMAN PPA PRICER <span style={{ color: "var(--accent-emerald)", fontWeight: 500 }}>// RISK ENGINE</span>
            </div>
            <div style={{ fontSize: "0.72rem", color: "var(--text-muted)", letterSpacing: "0.04em" }}>
              PAY-AS-PRODUCED • DE-LU BIDDING ZONE • DUCKDB COLUMNAR
            </div>
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "20px" }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "8px",
              background: "rgba(0, 245, 160, 0.08)",
              border: "1px solid rgba(0, 245, 160, 0.2)",
              padding: "5px 12px",
              borderRadius: "20px",
              fontSize: "0.75rem",
              color: "var(--accent-emerald)",
            }}
          >
            <div className="pulse-dot" />
            <span>FastAPI: 8000 &bull; DuckDB Live</span>
          </div>

          <button
            onClick={() => {
              runValuation();
              fetchDuckCurve();
            }}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              background: "rgba(255, 255, 255, 0.05)",
              border: "1px solid var(--border-subtle)",
              color: "var(--text-secondary)",
              padding: "6px 12px",
              borderRadius: "8px",
              fontSize: "0.8rem",
              cursor: "pointer",
            }}
          >
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
            Sync
          </button>
        </div>
      </header>

      {/* Main Grid Workspace */}
      <main
        style={{
          flex: 1,
          display: "grid",
          gridTemplateColumns: "360px 1fr",
          gap: "24px",
          padding: "24px 28px",
          maxWidth: "1800px",
          margin: "0 auto",
          width: "100%",
        }}
      >
        {/* LEFT COLUMN: ASSET & CONTRACT STRUCTURING CONSOLE */}
        <section
          className="glass-panel"
          style={{
            padding: "22px",
            display: "flex",
            flexDirection: "column",
            gap: "20px",
            height: "fit-content",
          }}
        >
          <div style={{ borderBottom: "1px solid var(--border-subtle)", paddingBottom: "12px" }}>
            <h2 style={{ fontSize: "0.95rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-primary)" }}>
              Asset & Contract Console
            </h2>
            <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "2px" }}>
              Configure asset technology and PPA settlement parameters
            </p>
          </div>

          {/* Technology Radio Cards */}
          <div>
            <label style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--text-secondary)", textTransform: "uppercase" }}>
              Technology Type
            </label>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "8px", marginTop: "8px" }}>
              {[
                { id: "solar_pv", label: "Solar PV", icon: Sun, color: "#f59e0b" },
                { id: "wind_onshore", label: "Wind Onshore", icon: Wind, color: "#00d9f5" },
                { id: "wind_offshore", label: "Wind Offshore", icon: Waves, color: "#8b5cf6" },
              ].map((item) => {
                const Icon = item.icon;
                const isSelected = tech === item.id;
                return (
                  <button
                    key={item.id}
                    id={`tech-select-${item.id}`}
                    onClick={() => handleTechChange(item.id)}
                    style={{
                      background: isSelected ? "rgba(0, 245, 160, 0.12)" : "rgba(255, 255, 255, 0.03)",
                      border: isSelected ? "1px solid var(--accent-emerald)" : "1px solid var(--border-subtle)",
                      borderRadius: "8px",
                      padding: "10px 6px",
                      cursor: "pointer",
                      display: "flex",
                      flexDirection: "column",
                      alignItems: "center",
                      gap: "6px",
                      color: isSelected ? "var(--accent-emerald)" : "var(--text-secondary)",
                      transition: "all 0.15s ease",
                    }}
                  >
                    <Icon size={18} color={isSelected ? "var(--accent-emerald)" : item.color} />
                    <span style={{ fontSize: "0.72rem", fontWeight: 600 }}>{item.label}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Benchmark Location */}
          <div>
            <label style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--text-secondary)", textTransform: "uppercase" }}>
              German Benchmark Cluster
            </label>
            <select
              id="location-select"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              style={{
                width: "100%",
                background: "#0d131f",
                border: "1px solid var(--border-subtle)",
                borderRadius: "8px",
                padding: "9px 12px",
                color: "var(--text-primary)",
                fontSize: "0.82rem",
                marginTop: "6px",
                outline: "none",
              }}
            >
              {locationsByTech[tech]?.map((loc) => (
                <option key={loc.id} value={loc.id}>
                  {loc.label}
                </option>
              ))}
            </select>
          </div>

          {/* Capacity Slider */}
          <div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <label style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--text-secondary)", textTransform: "uppercase" }}>
                Nameplate Capacity
              </label>
              <span style={{ fontSize: "0.82rem", fontWeight: 700, color: "var(--accent-cyan)", fontFamily: "var(--font-mono)" }}>
                {capacity} MW
              </span>
            </div>
            <input
              id="slider-capacity"
              type="range"
              min={5}
              max={250}
              step={5}
              value={capacity}
              onChange={(e) => setCapacity(Number(e.target.value))}
              style={{ marginTop: "8px" }}
            />
          </div>

          {/* Tenor Slider */}
          <div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <label style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--text-secondary)", textTransform: "uppercase" }}>
                Contract Tenor
              </label>
              <span style={{ fontSize: "0.82rem", fontWeight: 700, color: "var(--accent-emerald)", fontFamily: "var(--font-mono)" }}>
                {tenor} Years
              </span>
            </div>
            <input
              id="slider-tenor"
              type="range"
              min={1}
              max={15}
              step={1}
              value={tenor}
              onChange={(e) => setTenor(Number(e.target.value))}
              style={{ marginTop: "8px" }}
            />
          </div>

          {/* Market Baseload Price */}
          <div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <label style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--text-secondary)", textTransform: "uppercase" }}>
                Forward Baseload Price
              </label>
              <span style={{ fontSize: "0.82rem", fontWeight: 700, color: "var(--text-primary)", fontFamily: "var(--font-mono)" }}>
                {baseload.toFixed(1)} €/MWh
              </span>
            </div>
            <input
              id="slider-baseload"
              type="range"
              min={30}
              max={150}
              step={2.5}
              value={baseload}
              onChange={(e) => setBaseload(Number(e.target.value))}
              style={{ marginTop: "8px" }}
            />
          </div>

          {/* Balancing Cost & Risk Buffer */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
            <div>
              <label style={{ fontSize: "0.72rem", color: "var(--text-secondary)" }}>Balancing Fee</label>
              <input
                id="input-balancing"
                type="number"
                step={0.25}
                value={balancingCost}
                onChange={(e) => setBalancingCost(Number(e.target.value))}
                style={{
                  width: "100%",
                  background: "#0d131f",
                  border: "1px solid var(--border-subtle)",
                  borderRadius: "6px",
                  padding: "7px 10px",
                  color: "var(--text-primary)",
                  fontSize: "0.82rem",
                  marginTop: "4px",
                  fontFamily: "var(--font-mono)",
                }}
              />
            </div>

            <div>
              <label style={{ fontSize: "0.72rem", color: "var(--text-secondary)" }}>Risk Margin</label>
              <input
                id="input-risk-margin"
                type="number"
                step={0.25}
                value={riskMargin}
                onChange={(e) => setRiskMargin(Number(e.target.value))}
                style={{
                  width: "100%",
                  background: "#0d131f",
                  border: "1px solid var(--border-subtle)",
                  borderRadius: "6px",
                  padding: "7px 10px",
                  color: "var(--text-primary)",
                  fontSize: "0.82rem",
                  marginTop: "4px",
                  fontFamily: "var(--font-mono)",
                }}
              />
            </div>
          </div>

          {/* Floor Price Toggle */}
          <div style={{ background: "rgba(255, 255, 255, 0.02)", border: "1px solid var(--border-subtle)", borderRadius: "8px", padding: "12px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: "0.78rem", fontWeight: 600 }}>Downside Floor Guarantee</span>
              <input
                id="toggle-floor"
                type="checkbox"
                checked={enableFloor}
                onChange={(e) => setEnableFloor(e.target.checked)}
                style={{ cursor: "pointer", width: "16px", height: "16px", accentColor: "var(--accent-emerald)" }}
              />
            </div>

            {enableFloor && (
              <div style={{ marginTop: "10px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.72rem", color: "var(--text-secondary)" }}>
                  <span>Floor Level</span>
                  <span style={{ fontFamily: "var(--font-mono)", color: "var(--accent-emerald)" }}>{floorPrice.toFixed(1)} €/MWh</span>
                </div>
                <input
                  type="range"
                  min={-20}
                  max={40}
                  step={5}
                  value={floorPrice}
                  onChange={(e) => setFloorPrice(Number(e.target.value))}
                  style={{ marginTop: "6px" }}
                />
              </div>
            )}
          </div>

          {/* Action Button */}
          <button
            id="btn-run-valuation"
            onClick={runValuation}
            disabled={loading}
            style={{
              background: "linear-gradient(135deg, #00f5a0 0%, #00d9f5 100%)",
              color: "#07090e",
              border: "none",
              borderRadius: "10px",
              padding: "13px",
              fontWeight: 700,
              fontSize: "0.9rem",
              cursor: loading ? "not-allowed" : "pointer",
              boxShadow: "0 0 20px rgba(0, 245, 160, 0.3)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: "8px",
              transition: "transform 0.1s, box-shadow 0.1s",
              opacity: loading ? 0.7 : 1,
            }}
          >
            {loading ? (
              <>
                <RefreshCw size={18} className="animate-spin" />
                <span>Simulating Monte Carlo Paths...</span>
              </>
            ) : (
              <>
                <Sparkles size={18} />
                <span>Calculate Fair PPA Price</span>
              </>
            )}
          </button>
        </section>

        {/* RIGHT COLUMN: VALUATION METRICS & TABS */}
        <section style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
          {errorMsg && (
            <div style={{ background: "rgba(244, 63, 94, 0.15)", border: "1px solid var(--accent-rose)", borderRadius: "10px", padding: "14px 18px", color: "#fecdd3", fontSize: "0.85rem" }}>
              <strong>Error:</strong> {errorMsg}
            </div>
          )}

          {/* TOP 6 KPI METRIC CARDS */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: "14px" }}>
            {/* 1. Fair PPA Price */}
            <div className="glass-panel" style={{ padding: "16px", position: "relative", overflow: "hidden" }}>
              <div style={{ fontSize: "0.72rem", fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase" }}>
                Fair Fixed Strike
              </div>
              <div style={{ fontSize: "1.75rem", fontWeight: 800, marginTop: "6px" }} className="gradient-text-emerald">
                {result ? `${result.fair_ppa_fixed_price.toFixed(2)} €` : "--"}
              </div>
              <div style={{ fontSize: "0.72rem", color: "var(--text-secondary)", marginTop: "4px" }}>
                per MWh generated
              </div>
            </div>

            {/* 2. Marktwertfaktor */}
            <div className="glass-panel" style={{ padding: "16px" }}>
              <div style={{ fontSize: "0.72rem", fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase" }}>
                Marktwertfaktor
              </div>
              <div style={{ fontSize: "1.75rem", fontWeight: 800, color: "var(--accent-cyan)", marginTop: "6px" }}>
                {result ? `${(result.capture_factor_expected * 100).toFixed(1)}%` : "--"}
              </div>
              <div style={{ fontSize: "0.72rem", color: "var(--text-secondary)", marginTop: "4px" }}>
                Capture / Baseload
              </div>
            </div>

            {/* 3. Expected Generation */}
            <div className="glass-panel" style={{ padding: "16px" }}>
              <div style={{ fontSize: "0.72rem", fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase" }}>
                Expected Volume
              </div>
              <div style={{ fontSize: "1.75rem", fontWeight: 800, color: "var(--text-primary)", marginTop: "6px" }}>
                {result ? `${(result.expected_annual_generation_mwh / 1000).toFixed(1)}` : "--"} <span style={{ fontSize: "0.95rem" }}>GWh</span>
              </div>
              <div style={{ fontSize: "0.72rem", color: "var(--text-secondary)", marginTop: "4px" }}>
                P50: {result ? `${(result.risk_metrics.volume_p50_mwh / 1000).toFixed(1)} GWh` : "--"}
              </div>
            </div>

            {/* 4. Annual Cash Flow */}
            <div className="glass-panel" style={{ padding: "16px" }}>
              <div style={{ fontSize: "0.72rem", fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase" }}>
                Annual Revenue
              </div>
              <div style={{ fontSize: "1.75rem", fontWeight: 800, color: "var(--accent-amber)", marginTop: "6px" }}>
                {result ? `€${(result.expected_annual_revenue_ppa_eur / 1e6).toFixed(2)}M` : "--"}
              </div>
              <div style={{ fontSize: "0.72rem", color: "var(--text-secondary)", marginTop: "4px" }}>
                P90: {result ? `€${(result.risk_metrics.revenue_p90_eur / 1e6).toFixed(2)}M` : "--"}
              </div>
            </div>

            {/* 5. Value at Risk (95% VaR) */}
            <div className="glass-panel" style={{ padding: "16px" }}>
              <div style={{ fontSize: "0.72rem", fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase" }}>
                Downside VaR 95%
              </div>
              <div style={{ fontSize: "1.75rem", fontWeight: 800, color: "var(--accent-rose)", marginTop: "6px" }}>
                {result ? `€${(result.risk_metrics.var_95_eur / 1000).toFixed(0)}k` : "--"}
              </div>
              <div style={{ fontSize: "0.72rem", color: "var(--text-secondary)", marginTop: "4px" }}>
                Tail loss vs P50
              </div>
            </div>

            {/* 6. Negative Price Exposure */}
            <div className="glass-panel" style={{ padding: "16px" }}>
              <div style={{ fontSize: "0.72rem", fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase" }}>
                Negative Hours
              </div>
              <div style={{ fontSize: "1.75rem", fontWeight: 800, color: "#cbd5e1", marginTop: "6px" }}>
                {result ? `${result.risk_metrics.expected_negative_hours_annual.toFixed(0)}h` : "--"}
              </div>
              <div style={{ fontSize: "0.72rem", color: "var(--text-secondary)", marginTop: "4px" }}>
                {result ? `${result.risk_metrics.pct_negative_hours.toFixed(1)}% of year` : "--"}
              </div>
            </div>
          </div>

          {/* TABBED INTERACTIVE ANALYTICS PANELS */}
          <div className="glass-panel" style={{ padding: "20px", flex: 1 }}>
            {/* Tabs Bar */}
            <div style={{ display: "flex", gap: "10px", borderBottom: "1px solid var(--border-subtle)", paddingBottom: "14px" }}>
              {[
                { id: "waterfall", label: "📊 Pricing Waterfall", desc: "Decomposition" },
                { id: "fanchart", label: "🎲 Monte Carlo Fan Chart", desc: "P10/P50/P90" },
                { id: "duckcurve", label: "🦆 Cannibalization & Duck Curve", desc: "Diurnal Merit-Order" },
                { id: "negative", label: "⚠️ Negative Prices (EEG §51)", desc: "Regulatory Risk" },
                { id: "audit", label: "📋 Financial Summary Audit", desc: "Metrics" },
              ].map((tab) => {
                const isActive = activeTab === tab.id;
                return (
                  <button
                    key={tab.id}
                    id={`tab-${tab.id}`}
                    onClick={() => setActiveTab(tab.id as any)}
                    style={{
                      background: isActive ? "rgba(0, 245, 160, 0.1)" : "transparent",
                      border: isActive ? "1px solid var(--accent-emerald)" : "1px solid transparent",
                      borderRadius: "8px",
                      padding: "8px 16px",
                      color: isActive ? "var(--accent-emerald)" : "var(--text-secondary)",
                      fontWeight: isActive ? 700 : 500,
                      fontSize: "0.82rem",
                      cursor: "pointer",
                      transition: "all 0.15s ease",
                    }}
                  >
                    {tab.label}
                  </button>
                );
              })}
            </div>

            {/* TAB CONTENT 1: WATERFALL */}
            {activeTab === "waterfall" && result && (
              <div style={{ marginTop: "24px" }}>
                <div style={{ marginBottom: "18px" }}>
                  <h3 style={{ fontSize: "1.05rem", fontWeight: 700 }}>Pay-as-Produced Valuation Waterfall</h3>
                  <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginTop: "4px" }}>
                    From flat baseload power price down to the Fair Fixed Strike Price offered to the developer.
                  </p>
                </div>

                {/* Waterfall Visual Bars */}
                <div style={{ display: "flex", flexDirection: "column", gap: "12px", marginTop: "16px" }}>
                  {[
                    { label: "Forward Baseload Market Price", value: result.expected_baseload_price, type: "base", color: "#3b82f6", prefix: "" },
                    { label: "Cannibalization (Profile Haircut)", value: -result.cannibalization_discount, type: "deduction", color: "#f43f5e", prefix: "-" },
                    { label: "Generation-Weighted Capture Price", value: result.expected_capture_price, type: "subtotal", color: "#00d9f5", prefix: "" },
                    { label: "Balancing & Forecast Deviations", value: -result.balancing_cost, type: "deduction", color: "#f59e0b", prefix: "-" },
                    { label: "Off-taker Downside Risk Buffer", value: -result.risk_premium, type: "deduction", color: "#f59e0b", prefix: "-" },
                    { label: "Floor Guarantee Premium", value: result.floor_option_value, type: "addition", color: "#8b5cf6", prefix: "+" },
                    { label: "Fair Fixed PPA Price (K*)", value: result.fair_ppa_fixed_price, type: "final", color: "#00f5a0", prefix: "" },
                  ].map((row, idx) => (
                    <div key={idx} style={{ display: "grid", gridTemplateColumns: "260px 1fr 120px", alignItems: "center", gap: "16px" }}>
                      <span style={{ fontSize: "0.82rem", fontWeight: row.type === "final" ? 700 : 500, color: row.type === "final" ? "var(--accent-emerald)" : "var(--text-primary)" }}>
                        {row.label}
                      </span>
                      
                      {/* Bar Container */}
                      <div style={{ background: "rgba(255, 255, 255, 0.03)", height: "24px", borderRadius: "4px", position: "relative", overflow: "hidden" }}>
                        <div
                          style={{
                            height: "100%",
                            width: `${Math.min(Math.max((Math.abs(row.value) / 80) * 100, 4), 100)}%`,
                            background: row.color,
                            borderRadius: "4px",
                            opacity: row.type === "final" ? 1 : 0.85,
                            boxShadow: row.type === "final" ? "0 0 12px rgba(0, 245, 160, 0.4)" : "none",
                          }}
                        />
                      </div>

                      <span style={{ textAlign: "right", fontFamily: "var(--font-mono)", fontSize: "0.88rem", fontWeight: 700, color: row.color }}>
                        {row.prefix}{Math.abs(row.value).toFixed(2)} €/MWh
                      </span>
                    </div>
                  ))}
                </div>

                {/* Explanatory Callout */}
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px", marginTop: "28px" }}>
                  <div style={{ background: "rgba(244, 63, 94, 0.08)", border: "1px solid rgba(244, 63, 94, 0.2)", borderRadius: "10px", padding: "14px" }}>
                    <div style={{ fontWeight: 700, fontSize: "0.85rem", color: "var(--accent-rose)", display: "flex", alignItems: "center", gap: "6px" }}>
                      <TrendingDown size={16} /> Cannibalization Discount: -{result.cannibalization_discount.toFixed(2)} €/MWh
                    </div>
                    <p style={{ fontSize: "0.76rem", color: "#fecdd3", marginTop: "6px", lineHeight: "1.4" }}>
                      Due to the merit-order effect, market prices drop during hours when {tech.replace("_", " ")} generates.
                      The asset captures only <strong>{(result.capture_factor_expected * 100).toFixed(1)}%</strong> of the baseload market price.
                    </p>
                  </div>

                  <div style={{ background: "rgba(0, 245, 160, 0.08)", border: "1px solid rgba(0, 245, 160, 0.2)", borderRadius: "10px", padding: "14px" }}>
                    <div style={{ fontWeight: 700, fontSize: "0.85rem", color: "var(--accent-emerald)", display: "flex", alignItems: "center", gap: "6px" }}>
                      <Zap size={16} /> Contract Value Proposition
                    </div>
                    <p style={{ fontSize: "0.76rem", color: "#a7f3d0", marginTop: "6px", lineHeight: "1.4" }}>
                      Locking in <strong>{result.fair_ppa_fixed_price.toFixed(2)} €/MWh</strong> protects the developer from spot volatility,
                      guaranteeing bankable debt service coverage for project finance.
                    </p>
                  </div>
                </div>
              </div>
            )}

            {/* TAB CONTENT 2: MONTE CARLO FAN CHART */}
            {activeTab === "fanchart" && result && (
              <div style={{ marginTop: "24px" }}>
                <div style={{ marginBottom: "18px" }}>
                  <h3 style={{ fontSize: "1.05rem", fontWeight: 700 }}>Contract Revenue Trajectory (P10 - P50 - P90)</h3>
                  <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginTop: "4px" }}>
                    Simulated cash flows over {tenor} years incorporating inter-annual weather variation and panel/turbine degradation.
                  </p>
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "14px", marginBottom: "20px" }}>
                  <div style={{ background: "rgba(0, 245, 160, 0.06)", border: "1px solid rgba(0, 245, 160, 0.2)", borderRadius: "8px", padding: "12px" }}>
                    <span style={{ fontSize: "0.72rem", color: "var(--accent-emerald)", fontWeight: 700 }}>P10 (Optimistic High)</span>
                    <div style={{ fontSize: "1.3rem", fontWeight: 800, marginTop: "4px" }}>
                      €{(result.risk_metrics.revenue_p10_eur / 1e6).toFixed(2)}M / yr
                    </div>
                    <span style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>90th percentile weather & price</span>
                  </div>

                  <div style={{ background: "rgba(0, 217, 245, 0.06)", border: "1px solid rgba(0, 217, 245, 0.2)", borderRadius: "8px", padding: "12px" }}>
                    <span style={{ fontSize: "0.72rem", color: "var(--accent-cyan)", fontWeight: 700 }}>P50 (Expected Baseline)</span>
                    <div style={{ fontSize: "1.3rem", fontWeight: 800, marginTop: "4px" }}>
                      €{(result.risk_metrics.revenue_p50_eur / 1e6).toFixed(2)}M / yr
                    </div>
                    <span style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Median expected case</span>
                  </div>

                  <div style={{ background: "rgba(244, 63, 94, 0.06)", border: "1px solid rgba(244, 63, 94, 0.2)", borderRadius: "8px", padding: "12px" }}>
                    <span style={{ fontSize: "0.72rem", color: "var(--accent-rose)", fontWeight: 700 }}>P90 (Debt-Sizing Downside)</span>
                    <div style={{ fontSize: "1.3rem", fontWeight: 800, marginTop: "4px" }}>
                      €{(result.risk_metrics.revenue_p90_eur / 1e6).toFixed(2)}M / yr
                    </div>
                    <span style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Bank standard for loan coverage</span>
                  </div>
                </div>

                {/* Simulated Year by Year Table */}
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.8rem", textAlign: "left" }}>
                  <thead>
                    <tr style={{ borderBottom: "1px solid var(--border-subtle)", color: "var(--text-muted)" }}>
                      <th style={{ padding: "8px" }}>Operating Year</th>
                      <th style={{ padding: "8px" }}>P90 Downside Revenue</th>
                      <th style={{ padding: "8px" }}>P50 Expected Revenue</th>
                      <th style={{ padding: "8px" }}>P10 Optimistic Revenue</th>
                      <th style={{ padding: "8px" }}>Degradation Factor</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Array.from({ length: tenor }, (_, i) => {
                      const deg = (1 - 0.005) ** i;
                      return (
                        <tr key={i} style={{ borderBottom: "1px solid rgba(255, 255, 255, 0.03)" }}>
                          <td style={{ padding: "10px 8px", fontWeight: 600 }}>Year {i + 1}</td>
                          <td style={{ padding: "10px 8px", color: "var(--accent-rose)", fontFamily: "var(--font-mono)" }}>
                            €{((result.risk_metrics.revenue_p90_eur * deg) / 1e6).toFixed(3)}M
                          </td>
                          <td style={{ padding: "10px 8px", color: "var(--accent-cyan)", fontFamily: "var(--font-mono)" }}>
                            €{((result.risk_metrics.revenue_p50_eur * deg) / 1e6).toFixed(3)}M
                          </td>
                          <td style={{ padding: "10px 8px", color: "var(--accent-emerald)", fontFamily: "var(--font-mono)" }}>
                            €{((result.risk_metrics.revenue_p10_eur * deg) / 1e6).toFixed(3)}M
                          </td>
                          <td style={{ padding: "10px 8px", color: "var(--text-muted)" }}>{(deg * 100).toFixed(1)}%</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}

            {/* TAB CONTENT 3: DUCK CURVE */}
            {activeTab === "duckcurve" && (
              <div style={{ marginTop: "24px" }}>
                <div style={{ marginBottom: "18px" }}>
                  <h3 style={{ fontSize: "1.05rem", fontWeight: 700 }}>Diurnal Cannibalization & The German Duck Curve</h3>
                  <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginTop: "4px" }}>
                    Average 24-hour profile (UTC) showing midday spot price collapse coinciding with peak solar generation.
                  </p>
                </div>

                {duckCurve.length > 0 ? (
                  <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                    <div style={{ display: "grid", gridTemplateColumns: "70px 1fr 1fr 100px", fontSize: "0.72rem", color: "var(--text-muted)", fontWeight: 700, paddingBottom: "6px", borderBottom: "1px solid var(--border-subtle)" }}>
                      <span>Hour (UTC)</span>
                      <span>Day-Ahead Spot Price (€/MWh)</span>
                      <span>Solar Generation (GWh)</span>
                      <span style={{ textAlign: "right" }}>Neg. Hours</span>
                    </div>

                    {duckCurve.map((point) => (
                      <div key={point.hour_of_day_utc} style={{ display: "grid", gridTemplateColumns: "70px 1fr 1fr 100px", alignItems: "center", fontSize: "0.78rem", padding: "6px 0", borderBottom: "1px solid rgba(255, 255, 255, 0.02)" }}>
                        <span style={{ fontFamily: "var(--font-mono)", fontWeight: 600 }}>{String(point.hour_of_day_utc).padStart(2, "0")}:00</span>
                        
                        {/* Price bar */}
                        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                          <div style={{ width: `${Math.min(Math.max((point.avg_price_eur_mwh / 100) * 120, 10), 160)}px`, height: "14px", background: point.avg_price_eur_mwh < 40 ? "var(--accent-rose)" : "var(--accent-cyan)", borderRadius: "3px" }} />
                          <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.75rem", color: point.avg_price_eur_mwh < 40 ? "var(--accent-rose)" : "var(--text-primary)" }}>
                            {point.avg_price_eur_mwh.toFixed(1)} €
                          </span>
                        </div>

                        {/* Solar bar */}
                        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                          <div style={{ width: `${Math.min((point.avg_solar_mwh / 35000) * 140, 160)}px`, height: "14px", background: "var(--accent-amber)", borderRadius: "3px" }} />
                          <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.75rem" }}>
                            {(point.avg_solar_mwh / 1000).toFixed(1)} GWh
                          </span>
                        </div>

                        <span style={{ textAlign: "right", color: point.negative_price_occurrences > 0 ? "var(--accent-rose)" : "var(--text-muted)", fontWeight: 700 }}>
                          {point.negative_price_occurrences}
                        </span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div style={{ padding: "30px", textAlign: "center", color: "var(--text-muted)" }}>
                    Loading Duck Curve from DuckDB analytics...
                  </div>
                )}
              </div>
            )}

            {/* TAB CONTENT 4: NEGATIVE PRICES & EEG 51 */}
            {activeTab === "negative" && result && (
              <div style={{ marginTop: "24px" }}>
                <div style={{ marginBottom: "18px" }}>
                  <h3 style={{ fontSize: "1.05rem", fontWeight: 700 }}>Negative Price Risk & Regulatory Curtailment (EEG § 51)</h3>
                  <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginTop: "4px" }}>
                    Statutory subsidy cancellation and merchant cash flow drain during negative pricing intervals.
                  </p>
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "20px" }}>
                  <div style={{ background: "rgba(255, 255, 255, 0.02)", border: "1px solid var(--border-subtle)", borderRadius: "10px", padding: "18px" }}>
                    <h4 style={{ fontSize: "0.88rem", fontWeight: 700, color: "var(--accent-rose)" }}>Regulatory Framework: EEG § 51</h4>
                    <p style={{ fontSize: "0.78rem", color: "var(--text-secondary)", marginTop: "8px", lineHeight: "1.5" }}>
                      Under § 51 of the German Renewable Energy Sources Act (*Erneuerbare-Energien-Gesetz*), statutory feed-in support 
                      is <strong>completely cancelled</strong> when market prices are negative for consecutive hours (historical threshold: 3 to 6 consecutive hours).
                    </p>

                    <div style={{ marginTop: "16px", display: "flex", flexDirection: "column", gap: "8px" }}>
                      <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.8rem", borderBottom: "1px solid var(--border-subtle)", paddingBottom: "6px" }}>
                        <span style={{ color: "var(--text-muted)" }}>Expected Negative Hours / Year:</span>
                        <span style={{ fontWeight: 700, fontFamily: "var(--font-mono)" }}>{result.risk_metrics.expected_negative_hours_annual.toFixed(0)} hours</span>
                      </div>
                      <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.8rem", borderBottom: "1px solid var(--border-subtle)", paddingBottom: "6px" }}>
                        <span style={{ color: "var(--text-muted)" }}>% of Total Hours:</span>
                        <span style={{ fontWeight: 700, fontFamily: "var(--font-mono)", color: "var(--accent-rose)" }}>{result.risk_metrics.pct_negative_hours.toFixed(1)}%</span>
                      </div>
                      <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.8rem", paddingBottom: "6px" }}>
                        <span style={{ color: "var(--text-muted)" }}>Unhedged Negative Cash Drain:</span>
                        <span style={{ fontWeight: 700, fontFamily: "var(--font-mono)", color: "var(--accent-rose)" }}>€{result.risk_metrics.unhedged_negative_cash_drain_eur.toLocaleString()} / yr</span>
                      </div>
                    </div>
                  </div>

                  <div style={{ background: "rgba(255, 255, 255, 0.02)", border: "1px solid var(--border-subtle)", borderRadius: "10px", padding: "18px" }}>
                    <h4 style={{ fontSize: "0.88rem", fontWeight: 700, color: "var(--accent-cyan)" }}>Asset Mitigation Strategies</h4>
                    <ul style={{ fontSize: "0.78rem", color: "var(--text-secondary)", marginTop: "10px", lineHeight: "1.6", paddingLeft: "16px" }}>
                      <li><strong>Automated Inverter Curtailment:</strong> Remotely throttle solar inverters or pitch wind turbine blades when spot price dips below balancing fees.</li>
                      <li><strong>BESS (Battery Energy Storage) Co-location:</strong> Absorb negative-price power midday, discharge into evening peak (6:00 PM – 9:00 PM).</li>
                      <li><strong>Contractual Floor Clause:</strong> Introduce a 0.0 €/MWh floor where the off-taker absorbs negative price risk in exchange for a lower fixed strike.</li>
                    </ul>
                  </div>
                </div>
              </div>
            )}

            {/* TAB CONTENT 5: AUDIT SUMMARY */}
            {activeTab === "audit" && result && (
              <div style={{ marginTop: "24px" }}>
                <div style={{ marginBottom: "18px" }}>
                  <h3 style={{ fontSize: "1.05rem", fontWeight: 700 }}>Contract Audit & Financial Summary</h3>
                  <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginTop: "4px" }}>
                    Complete audit trail of valuation results, risk parameters, and financial outputs.
                  </p>
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "14px" }}>
                  {Object.entries(result.summary_table).map(([key, val]) => (
                    <div key={key} style={{ background: "rgba(255, 255, 255, 0.02)", border: "1px solid var(--border-subtle)", borderRadius: "6px", padding: "10px 14px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span style={{ fontSize: "0.78rem", color: "var(--text-secondary)" }}>{key}</span>
                      <span style={{ fontSize: "0.82rem", fontWeight: 700, fontFamily: "var(--font-mono)", color: "var(--accent-emerald)" }}>{String(val)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </section>
      </main>
    </div>
  );
}
