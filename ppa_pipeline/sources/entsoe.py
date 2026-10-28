import os
import logging
from typing import Optional, Dict
import requests
import xml.etree.ElementTree as ET
import pandas as pd
from ppa_pipeline.config import DEFAULT_TIMEZONE

logger = logging.getLogger(__name__)

ENTSOE_ENDPOINT = "https://web-api.tp.entsoe.eu/api"
# ENTSO-E Area code for German-Luxembourg Bidding Zone
GERMANY_LU_EIC = "10Y1001A1001A82H"


class EntsoeClient:
    """Client for the ENTSO-E Transparency Platform API.
    Requires ENTSOE_API_TOKEN (free registration at https://transparency.entsoe.eu/).
    """

    def __init__(self, api_token: Optional[str] = None, timeout: int = 30):
        self.api_token = api_token or os.getenv("ENTSOE_API_TOKEN")
        self.session = requests.Session()
        self.timeout = timeout

    @property
    def is_configured(self) -> bool:
        return bool(self.api_token)

    def fetch_day_ahead_prices(self, start_date: str, end_date: str) -> pd.DataFrame:
        """Fetch Day-Ahead Prices (Document Type A44) from ENTSO-E.
        Dates format: YYYY-MM-DD
        """
        if not self.is_configured:
            raise ValueError(
                "ENTSOE_API_TOKEN is not configured. "
                "Provide an API token or use the SMARD client (no key required)."
            )

        start_period = pd.to_datetime(start_date).strftime("%Y%m%d0000")
        end_period = (pd.to_datetime(end_date) + pd.Timedelta(days=1)).strftime("%Y%m%d0000")

        params = {
            "securityToken": self.api_token,
            "documentType": "A44",
            "in_Domain": GERMANY_LU_EIC,
            "out_Domain": GERMANY_LU_EIC,
            "periodStart": start_period,
            "periodEnd": end_period,
        }

        resp = self.session.get(ENTSOE_ENDPOINT, params=params, timeout=self.timeout)
        resp.raise_for_status()

        # Parse XML response
        root = ET.fromstring(resp.content)
        # ENTSO-E XML uses namespace
        ns = {"ns": root.tag.split("}")[0].strip("{")} if "}" in root.tag else {}
        find_prefix = "ns:" if ns else ""

        records = []
        for ts in root.findall(f".//{find_prefix}TimeSeries", ns):
            period = ts.find(f"{find_prefix}Period", ns)
            if period is None:
                continue
            time_interval = period.find(f"{find_prefix}timeInterval", ns)
            start_str = time_interval.find(f"{find_prefix}start", ns).text
            start_time = pd.to_datetime(start_str, utc=True)

            points = period.findall(f"{find_prefix}Point", ns)
            for pt in points:
                pos = int(pt.find(f"{find_prefix}position", ns).text)
                price = float(pt.find(f"{find_prefix}price.amount", ns).text)
                point_time = start_time + pd.Timedelta(hours=pos - 1)
                records.append({
                    "timestamp_utc": point_time,
                    "price_eur_mwh": price,
                    "bidding_zone": "DE-LU"
                })

        df = pd.DataFrame(records)
        if not df.empty:
            df["timestamp_cet"] = df["timestamp_utc"].dt.tz_convert(DEFAULT_TIMEZONE).dt.strftime("%Y-%m-%d %H:%M:%S")
            df = df.sort_values("timestamp_utc").drop_duplicates(subset=["timestamp_utc"])
        return df
