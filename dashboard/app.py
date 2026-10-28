import os
import sys
from pathlib import Path
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px

# Ensure project root is in sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from ppa_pipeline.storage.duckdb_manager import DuckDBManager
from ppa_pipeline.models.generation import AssetSpecification, TechnologyType
from ppa_pipeline.models.price_simulation import SimulationConfig
from ppa_pipeline.pricing.ppa_pricer import PayAsProducedPricer, PpaContractStructure
from ppa_pipeline.analytics.ppa_metrics import PpaRiskAnalytics

st.set_page_config(
    page_title="German Renewable PPA Pricing & Risk Engine",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for dark institutional energy trading terminal styling
st.markdown("""
<style>
    .metric-card {
        background-color: #1e222d;
        border: 1px solid #2e3546;
        border-radius: 8px;
        padding: 18px;
        margin-bottom: 12px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
    }
    .metric-title {
        color: #8f9cae;
        font-size: 0.85rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 6px;
    }
    .metric-value {
        color: #00d4aa;
        font-size: 1.85rem;
        font-weight: 700;
        margin-bottom: 4px;
    }
    .metric-sub {
        color: #a0aec0;
        font-size: 0.8rem;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 4px 4px 0 0;
        padding: 10px 18px;
        background-color: #151922;
        color: #94a3b8;
    }
    .stTabs [aria-selected="true"] {
        background-color: #262c3a !important;
        color: #00d4aa !important;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def get_db():
    return DuckDBManager()


@st.cache_data(ttl=600)
def load_historical_data():
    db = get_db()
    prices_df = db.query("SELECT * FROM market_prices ORDER BY timestamp_utc;")
    weather_df = db.query("SELECT * FROM weather_timeseries ORDER BY timestamp_utc;")
    return prices_df, weather_df


# Header
st.title("⚡ German Renewable PPA Pricing & Risk Engine")
st.markdown(
    "**Flagship Pay-as-Produced (PaP) Valuation Model** for German Solar and Wind assets. "
    "Simulates capture prices, profile cannibalization haircuts, balancing costs, and negative pricing exposure."
)

# Sidebar Controls
st.sidebar.header("🛠️ Asset & Contract Configuration")

tech_choice = st.sidebar.selectbox(
    "Generation Asset Technology",
    options=["Solar PV", "Onshore Wind", "Offshore Wind"],
    index=0,
)
tech_map = {
    "Solar PV": (TechnologyType.SOLAR_PV, "bavaria_solar"),
    "Onshore Wind": (TechnologyType.WIND_ONSHORE, "lower_saxony_wind"),
    "Offshore Wind": (TechnologyType.WIND_OFFSHORE, "north_sea_offshore"),
}
tech_enum, default_loc = tech_map[tech_choice]

capacity_mw = st.sidebar.slider("Nameplate Capacity (MW)", min_value=5.0, max_value=250.0, value=50.0, step=5.0)

location_options = {
    "Bavaria (High Solar Irradiance Hub)": "bavaria_solar",
    "Brandenburg (Eastern Solar Belt)": "brandenburg_solar",
    "Lower Saxony (High-Yield Onshore Wind)": "lower_saxony_wind",
    "Schleswig-Holstein (Coastal Wind Corridor)": "schleswig_wind",
    "North Sea (German Bight Offshore Cluster)": "north_sea_offshore",
}
selected_loc_name = st.sidebar.selectbox(
    "Benchmark Cluster Location",
    options=list(location_options.keys()),
    index=0 if tech_choice == "Solar PV" else (2 if tech_choice == "Onshore Wind" else 4),
)
selected_location_id = location_options[selected_loc_name]

tenor_years = st.sidebar.slider("PPA Contract Tenor (Years)", min_value=1, max_value=15, value=5, step=1)

st.sidebar.markdown("---")
st.sidebar.subheader("📈 Market & Structuring Terms")

expected_baseload = st.sidebar.number_input(
    "Forward Baseload Market Price (€/MWh)",
    min_value=20.0,
    max_value=200.0,
    value=65.0,
    step=2.5,
)

balancing_cost = st.sidebar.slider(
    "Balancing / Scheduling Cost (€/MWh)",
    min_value=0.5,
    max_value=6.0,
    value=2.50,
    step=0.25,
    help="Cost charged by off-taker for day-ahead forecast deviations and imbalance penalties.",
)

risk_margin = st.sidebar.slider(
    "Off-taker Risk Buffer / Margin (€/MWh)",
    min_value=0.0,
    max_value=5.0,
    value=1.50,
    step=0.25,
    help="Capital cost and downside volume/shape risk buffer deducted by off-taker.",
)

enable_floor = st.sidebar.checkbox("Include Downside Floor Guarantee", value=False)
floor_price = None
if enable_floor:
    floor_price = st.sidebar.number_input("Floor Price Level (€/MWh)", min_value=-50.0, max_value=50.0, value=0.0, step=5.0)

num_scenarios = st.sidebar.select_slider(
    "Monte Carlo Iterations",
    options=[100, 250, 500, 1000],
    value=500,
)

# Load data and run valuation
prices_df, weather_all = load_historical_data()

if prices_df.empty or weather_all.empty:
    st.error("No historical data found in DuckDB. Please run `python main.py` first to ingest German market & weather data.")
    st.stop()

# Filter weather for selected location
weather_filtered = weather_all[weather_all["location_id"] == selected_location_id]
if weather_filtered.empty:
    weather_filtered = weather_all.head(744)

# Create asset spec & contract
asset_spec = AssetSpecification(
    name=f"{tech_choice} {capacity_mw}MW",
    technology=tech_enum,
    capacity_mw=capacity_mw,
    location_id=selected_location_id,
)

contract = PpaContractStructure(
    contract_name=f"{tenor_years}Y Pay-as-Produced PPA",
    tenor_years=tenor_years,
    balancing_cost_eur_mwh=balancing_cost,
    risk_premium_eur_mwh=risk_margin,
    floor_price_eur_mwh=floor_price,
)

sim_config = SimulationConfig(
    num_scenarios=num_scenarios,
    expected_mean_price=expected_baseload,
)

pricer = PayAsProducedPricer(
    historical_market_df=prices_df,
    weather_df=weather_filtered,
    sim_config=sim_config,
)

with st.spinner("Executing Monte Carlo paths and PPA pricing waterfall..."):
    val_res = pricer.price_asset(asset_spec=asset_spec, contract=contract, expected_baseload_override=expected_baseload)

rm = val_res.risk_metrics

# ----------------- TOP KPI METRIC CARDS -----------------
col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">Fair Fixed PPA Price</div>
        <div class="metric-value">{val_res.fair_ppa_fixed_price:.2f} €</div>
        <div class="metric-sub">per MWh generated</div>
    </div>
    """, unsafe_allow_html=True)

with col2:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">Marktwertfaktor (MWF)</div>
        <div class="metric-value">{val_res.capture_factor_expected * 100:.1f}%</div>
        <div class="metric-sub">Capture / Baseload Ratio</div>
    </div>
    """, unsafe_allow_html=True)

with col3:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">Expected Generation</div>
        <div class="metric-value">{val_res.expected_annual_generation_mwh / 1000:.1f} GWh</div>
        <div class="metric-sub">P50: {rm.volume_p50_mwh / 1000:.1f} GWh/yr</div>
    </div>
    """, unsafe_allow_html=True)

with col4:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">Annual PPA Cash Flow</div>
        <div class="metric-value">€{val_res.expected_annual_revenue_ppa_eur / 1e6:.2f}M</div>
        <div class="metric-sub">P90 Downside: €{rm.revenue_p90_eur / 1e6:.2f}M</div>
    </div>
    """, unsafe_allow_html=True)

with col5:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">Negative Price Hours</div>
        <div class="metric-value">{rm.expected_negative_hours_annual:.0f} hrs</div>
        <div class="metric-sub">{rm.pct_negative_hours:.1f}% of total hours</div>
    </div>
    """, unsafe_allow_html=True)

# ----------------- TABS SECTION -----------------
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Pricing Waterfall",
    "🎲 Monte Carlo Risk & Fan Chart",
    "🦆 Cannibalization & Duck Curve",
    "⚠️ Negative Price & EEG §51",
    "🔍 Historical Data Explorer",
])

# TAB 1: PRICING WATERFALL
with tab1:
    st.subheader("Pay-as-Produced PPA Pricing Waterfall Breakdown")
    st.markdown(
        "Demonstrates step-by-step how the **Fair Fixed PPA Price** is derived from the flat baseload price, "
        "incorporating the cannibalization profile haircut, balancing charges, and off-taker risk margin."
    )

    wf_data = val_res.waterfall_breakdown()
    x_labels = list(wf_data.keys())
    y_values = list(wf_data.values())

    measure = ["absolute", "relative", "total", "relative", "relative", "relative", "total"]

    fig_wf = go.Figure(go.Waterfall(
        name="PPA Waterfall",
        orientation="v",
        measure=measure,
        x=x_labels,
        textposition="outside",
        text=[f"{v:+.2f} €" if m == "relative" else f"{v:.2f} €" for v, m in zip(y_values, measure)],
        y=y_values,
        connector={"line": {"color": "#64748b"}},
        decreasing={"marker": {"color": "#ef4444"}},
        increasing={"marker": {"color": "#10b981"}},
        totals={"marker": {"color": "#0ea5e9"}},
    ))

    fig_wf.update_layout(
        template="plotly_dark",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        height=480,
        yaxis_title="Price (EUR / MWh)",
        xaxis_tickangle=-20,
        margin=dict(l=40, r=40, t=20, b=80),
    )
    st.plotly_chart(fig_wf, use_container_width=True)

    c_left, c_right = st.columns(2)
    with c_left:
        st.info(f"""
        **Profile Cannibalization Haircut: -{val_res.cannibalization_discount:.2f} €/MWh**
        Because {tech_choice} output is concentrated when many peers generate, power price during operating hours is 
        suppressed from **{val_res.expected_baseload_price:.2f} €** down to **{val_res.expected_capture_price:.2f} €/MWh**.
        """)
    with c_right:
        st.success(f"""
        **Fixed PPA Certainty vs. Merchant Downside**
        Under the PPA, the generator locks in **{val_res.fair_ppa_fixed_price:.2f} €/MWh**, eliminating 
        merchant spot price volatility and downside Value at Risk (VaR 95%: **€{rm.var_95_eur:,.0f}**).
        """)

# TAB 2: MONTE CARLO & FAN CHART
with tab2:
    st.subheader(f"Monte Carlo Simulation ({num_scenarios} Correlated Scenarios over {tenor_years} Years)")

    col_m1, col_m2 = st.columns(2)

    with col_m1:
        st.markdown("#### Capture Price Distribution Across Paths")
        cap_prices = np.random.normal(rm.capture_price_mean_eur_mwh, rm.capture_price_std_eur_mwh, num_scenarios)
        fig_hist = px.histogram(
            x=cap_prices,
            nbins=30,
            color_discrete_sequence=["#00d4aa"],
            labels={"x": "Realized Capture Price (EUR/MWh)"},
            template="plotly_dark",
        )
        fig_hist.add_vline(x=rm.capture_price_p50_eur_mwh, line_dash="dash", line_color="#38bdf8", annotation_text=f"P50: {rm.capture_price_p50_eur_mwh:.2f}€")
        fig_hist.add_vline(x=rm.capture_price_p90_eur_mwh, line_dash="dot", line_color="#ef4444", annotation_text=f"P90: {rm.capture_price_p90_eur_mwh:.2f}€")
        fig_hist.update_layout(height=350, plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", showlegend=False)
        st.plotly_chart(fig_hist, use_container_width=True)

    with col_m2:
        st.markdown("#### Annual Contract Revenue Uncertainty")
        revenues_m = np.random.normal(rm.revenue_mean_eur / 1e6, rm.revenue_std_eur / 1e6, num_scenarios)
        fig_rev = px.histogram(
            x=revenues_m,
            nbins=30,
            color_discrete_sequence=["#f59e0b"],
            labels={"x": "Annual Revenue (Million EUR)"},
            template="plotly_dark",
        )
        fig_rev.add_vline(x=rm.revenue_p50_eur / 1e6, line_dash="dash", line_color="#38bdf8", annotation_text=f"P50: €{rm.revenue_p50_eur / 1e6:.2f}M")
        fig_rev.add_vline(x=rm.revenue_p90_eur / 1e6, line_dash="dot", line_color="#ef4444", annotation_text=f"P90: €{rm.revenue_p90_eur / 1e6:.2f}M")
        fig_rev.update_layout(height=350, plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", showlegend=False)
        st.plotly_chart(fig_rev, use_container_width=True)

    # Fan chart across contract years
    st.markdown("#### Contract Revenue Fan Chart (P10 - P50 - P90)")
    years = [f"Year {i}" for i in range(1, tenor_years + 1)]
    deg_rate = 0.005 if tech_choice == "Solar PV" else 0.002
    p50_path = [(rm.revenue_p50_eur / 1e6) * ((1 - deg_rate) ** i) for i in range(tenor_years)]
    p10_path = [(rm.revenue_p10_eur / 1e6) * ((1 - deg_rate) ** i) for i in range(tenor_years)]
    p90_path = [(rm.revenue_p90_eur / 1e6) * ((1 - deg_rate) ** i) for i in range(tenor_years)]

    fig_fan = go.Figure()
    fig_fan.add_trace(go.Scatter(x=years, y=p10_path, mode="lines", line=dict(color="#10b981", width=1), name="P10 (Optimistic High)"))
    fig_fan.add_trace(go.Scatter(x=years, y=p90_path, mode="lines", fill="tonexty", fillcolor="rgba(16, 185, 129, 0.15)", line=dict(color="#ef4444", width=1), name="P90 (Conservative Downside)"))
    fig_fan.add_trace(go.Scatter(x=years, y=p50_path, mode="lines+markers", line=dict(color="#38bdf8", width=3), name="P50 Expected Baseline"))

    fig_fan.update_layout(
        template="plotly_dark",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        height=380,
        yaxis_title="Annual Cash Flow (Million EUR)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    st.plotly_chart(fig_fan, use_container_width=True)

# TAB 3: CANNIBALIZATION DUCK CURVE
with tab3:
    st.subheader("Diurnal Cannibalization & The German 'Duck Curve'")
    st.markdown(
        "Hourly average profile showing how solar and wind generation depress German wholesale power prices "
        "during peak generation hours (the Merit-Order effect)."
    )

    db = get_db()
    analytics = PpaRiskAnalytics(db=db)
    diurnal_df = analytics.get_solar_cannibalization_profile()

    if not diurnal_df.empty:
        fig_diurnal = go.Figure()

        # Prices on primary y-axis
        fig_diurnal.add_trace(go.Scatter(
            x=diurnal_df["hour_of_day_utc"],
            y=diurnal_df["avg_price_eur_mwh"],
            name="Day-Ahead Price (€/MWh)",
            line=dict(color="#f43f5e", width=3),
            yaxis="y1",
        ))

        # Solar on secondary y-axis
        fig_diurnal.add_trace(go.Bar(
            x=diurnal_df["hour_of_day_utc"],
            y=diurnal_df["avg_solar_mwh"] / 1000,
            name="German Solar Generation (GWh)",
            marker_color="rgba(251, 191, 36, 0.6)",
            yaxis="y2",
        ))

        # Wind on secondary y-axis
        fig_diurnal.add_trace(go.Bar(
            x=diurnal_df["hour_of_day_utc"],
            y=diurnal_df["avg_wind_onshore_mwh"] / 1000,
            name="German Wind Generation (GWh)",
            marker_color="rgba(56, 189, 248, 0.5)",
            yaxis="y2",
        ))

        fig_diurnal.update_layout(
            template="plotly_dark",
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            height=450,
            xaxis=dict(title="Hour of Day (UTC)", tickmode="linear", tick0=0, dtick=2),
            yaxis=dict(title=dict(text="Electricity Price (EUR/MWh)", font=dict(color="#f43f5e")), tickfont=dict(color="#f43f5e")),
            yaxis2=dict(title=dict(text="Generation (GWh)", font=dict(color="#fbbf24")), tickfont=dict(color="#fbbf24"), overlaying="y", side="right"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            barmode="stack",
        )
        st.plotly_chart(fig_diurnal, use_container_width=True)

# TAB 4: NEGATIVE PRICES & EEG 51
with tab4:
    st.subheader("⚠️ Negative Price Risk & Regulatory Curtailment (EEG § 51)")
    st.markdown("""
    Under German Renewable Energy Act (**EEG § 51**), when Day-Ahead prices are negative for consecutive hours 
    (3 to 6 consecutive hours depending on asset commissioning date), government feed-in subsidies are **suspended**.
    For merchant PPAs, generating during negative hours represents direct cash outflow.
    """)

    c_n1, c_n2 = st.columns(2)
    with c_n1:
        st.metric("Expected Negative Pricing Hours", f"{rm.expected_negative_hours_annual:.0f} hrs/yr", f"{rm.pct_negative_hours:.1f}% of year")
        st.metric("Unhedged Negative Cash Drain", f"€{rm.unhedged_negative_cash_drain_eur:,.0f} / year", "direct loss if uncurtailed")

    with c_n2:
        st.markdown("#### Negative Price Mitigation Strategies:")
        st.markdown("""
        * **Automated Dispatch Curtailment:** Remotely turn off inverters when spot price dips below balancing cost.
        * **Battery Energy Storage (BESS) Co-location:** Absorb cheap or negative energy mid-day, discharge into the evening peak (6pm-9pm).
        * **Floor Guarantee Settlement Clause:** Add a PPA contractual floor at 0.0 €/MWh where buyer absorbs or shares negative price risk.
        """)

# TAB 5: HISTORICAL DATA EXPLORER
with tab5:
    st.subheader("DuckDB Data Warehouse Tables & Metrics")
    table_choice = st.selectbox("Select Table / Analytical View", ["v_monthly_capture_metrics", "market_prices", "weather_timeseries"])
    db = get_db()
    view_df = db.query(f"SELECT * FROM {table_choice} LIMIT 50;")
    st.dataframe(view_df, use_container_width=True)

st.markdown("---")
st.caption("PPA Pricing and Risk Engine • Built with DuckDB, Open-Meteo ERA5, SMARD, and Streamlit.")
