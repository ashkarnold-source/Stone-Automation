import pandas as pd
import io
from typing import List, Dict

COLUMN_MAP = {
    "company": "company_name",
    "company_name": "company_name",
    "agency": "company_name",
    "agency_name": "company_name",
    "organization": "company_name",
    "org": "company_name",
    "name": "contact_name",
    "contact": "contact_name",
    "contact_name": "contact_name",
    "full_name": "contact_name",
    "first_name": "_first_name",
    "last_name": "_last_name",
    "title": "title",
    "job_title": "title",
    "position": "title",
    "role": "title",
    "email": "email",
    "email_address": "email",
    "phone": "phone",
    "phone_number": "phone",
    "mobile": "phone",
    "cell": "phone",
    "linkedin": "linkedin_url",
    "linkedin_url": "linkedin_url",
    "linkedin_profile": "linkedin_url",
    "revenue": "revenue_tier",
    "annual_revenue": "revenue_tier",
    "revenue_estimate": "revenue_tier",
    "ownership": "ownership_type",
    "ownership_type": "ownership_type",
    "type": "ownership_type",
    "company_type": "ownership_type",
    "state": "state",
    "geography": "state",
    "region": "state",
    "city": "city",
    "notes": "notes",
    "note": "notes",
    "comments": "notes",
}

REVENUE_MAP = {
    "5m": "5m_10m", "5-10": "5m_10m", "5m-10m": "5m_10m",
    "10m": "10m_25m", "10-25": "10m_25m", "10m-25m": "10m_25m",
    "25m": "25m_plus", "25+": "25m_plus", "25m+": "25m_plus",
    "under 5": "under_5m", "<5m": "under_5m",
}

OWNERSHIP_MAP = {
    "independent": "independent", "indie": "independent", "private": "independent",
    "pe": "pe_backed", "pe-backed": "pe_backed", "private equity": "pe_backed",
    "chain": "regional_chain", "regional": "regional_chain",
}


def normalize_revenue(value: str) -> str:
    if not value:
        return None
    v = str(value).lower().strip().replace(",", "").replace("$", "").replace(" ", "")
    for k, mapped in REVENUE_MAP.items():
        if k in v:
            return mapped
    try:
        num = float(v.replace("m", "000000").replace("k", "000"))
        if num < 5_000_000:
            return "under_5m"
        elif num < 10_000_000:
            return "5m_10m"
        elif num < 25_000_000:
            return "10m_25m"
        else:
            return "25m_plus"
    except ValueError:
        return None


def normalize_ownership(value: str) -> str:
    if not value:
        return None
    v = str(value).lower().strip()
    for k, mapped in OWNERSHIP_MAP.items():
        if k in v:
            return mapped
    return None


def parse_csv(file_bytes: bytes) -> List[Dict]:
    df = pd.read_csv(io.BytesIO(file_bytes))
    df.columns = [c.lower().strip().replace(" ", "_") for c in df.columns]

    mapped = {}
    for col in df.columns:
        target = COLUMN_MAP.get(col)
        if target:
            mapped[target] = df[col]

    # Combine first/last name if separate columns
    if "_first_name" in mapped and "_last_name" in mapped:
        mapped["contact_name"] = mapped["_first_name"].fillna("") + " " + mapped["_last_name"].fillna("")
        mapped["contact_name"] = mapped["contact_name"].str.strip()
        del mapped["_first_name"]
        del mapped["_last_name"]

    records = []
    count = len(df)
    for i in range(count):
        row = {k: (str(v.iloc[i]).strip() if pd.notna(v.iloc[i]) else None)
               for k, v in mapped.items()}

        if not row.get("company_name"):
            continue

        if row.get("revenue_tier"):
            row["revenue_tier"] = normalize_revenue(row["revenue_tier"])
        if row.get("ownership_type"):
            row["ownership_type"] = normalize_ownership(row["ownership_type"])

        row["source"] = "csv_upload"
        records.append(row)

    return records
