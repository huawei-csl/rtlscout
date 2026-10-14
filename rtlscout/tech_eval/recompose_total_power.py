import re
from pathlib import Path
import pandas as pd

NUM = r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?'  # 1.23, .5, 1e-3, 2.3E+4

def parse_power_report(filepath: str | Path) -> pd.DataFrame:
    """
    Parse an OpenROAD `report_power` output like:

    Group                  Internal  Switching    Leakage      Total
                              Power      Power      Power      Power (Watts)
    ----------------------------------------------------------------
    Sequential             1.98e-06   8.33e-08   6.15e-10   2.06e-06  25.0%
    ...
    ----------------------------------------------------------------
    Total                  5.24e-06   2.98e-06   1.64e-08   8.24e-06 100.0%
                              63.6%      36.2%       0.2%

    Returns a DataFrame with columns (in Watts):
      Group, Internal Power (W), Switching Power (W), Leakage Power (W), Total Power (W)
    """
    lines = Path(filepath).read_text().splitlines()

    # Find the first dashed separator after the header block
    dash_idx = next((i for i, ln in enumerate(lines) if re.match(r'^\s*-{3,}\s*$', ln)), None)
    if dash_idx is None:
        raise ValueError("Could not locate table separator (---) in report.")

    # Parse lines from after the dashed line until the 'Total' row (inclusive)
    data = []
    row_re = re.compile(
        rf'^\s*(?P<group>\S.+?\S)\s+'
        rf'(?P<int>{NUM})\s+'
        rf'(?P<sw>{NUM})\s+'
        rf'(?P<leak>{NUM})\s+'
        rf'(?P<tot>{NUM})\s+'
        rf'(?P<pct>{NUM})%\s*$'
    )

    i = dash_idx + 1
    while i < len(lines):
        ln = lines[i].strip()
        # Stop if we hit another dashed line or a blank line
        if not ln or re.match(r'^-+$', ln):
            i += 1
            continue

        # The trailing percentages line (like "63.6% 36.2% 0.2%") has only % tokens — skip it
        if re.fullmatch(r'(?:\s*' + NUM + r'%\s*){1,}', ln):
            i += 1
            continue

        m = row_re.match(lines[i])
        if not m:
            # If we've already consumed the main rows and can't parse further, break
            # (This keeps the parser tolerant to footers or unexpected lines.)
            # print(f"Skipping unrecognized line: {lines[i]}")
            i += 1
            continue

        grp = m.group('group')
        data.append({
            "Group": grp,
            "Internal Power (W)": float(m.group('int')),
            "Switching Power (W)": float(m.group('sw')),
            "Leakage Power (W)" : float(m.group('leak')),
            "Total Power (W)"   : float(m.group('tot')),
            # "Percentage"      : float(m.group('pct'))  # available if you need it
        })

        # include rows until (and including) 'Total'
        if grp.strip().lower() == 'total':
            break

        i += 1

    if not data:
        raise ValueError("No data rows parsed from power report.")
    return pd.DataFrame(data)[
        ["Group","Internal Power (W)","Switching Power (W)","Leakage Power (W)","Total Power (W)"]
    ]

def summarize_power_report(filepath: str | Path) -> pd.DataFrame:
    df = parse_power_report(filepath)
    # If the report already has a 'Total' row, prefer it; else sum groups.
    total_row = df[df["Group"].str.strip().str.lower() == "total"]
    if not total_row.empty:
        tot = total_row.iloc[0]
        return pd.DataFrame([{
            "Total Internal Power (W)": tot["Internal Power (W)"],
            "Total Switching Power (W)": tot["Switching Power (W)"],
            "Total Leakage Power (W)" : tot["Leakage Power (W)"],
            "Total Power (W)"         : tot["Total Power (W)"],
        }])
    sums = df[["Internal Power (W)","Switching Power (W)","Leakage Power (W)","Total Power (W)"]].sum()
    return pd.DataFrame([{
        "Total Internal Power (W)": sums["Internal Power (W)"],
        "Total Switching Power (W)": sums["Switching Power (W)"],
        "Total Leakage Power (W)" : sums["Leakage Power (W)"],
        "Total Power (W)"         : sums["Total Power (W)"],
    }])

# ===== Example usage =====
if __name__ == "__main__":
    report_path = Path("result/power.rpt")   # adjust if needed
    summary = summarize_power_report(report_path)
    summary.to_parquet("result/post_synth_power.parquet", index=False)
    print(summary)

# (Optional) save the per-group breakdown too:
# per_group = parse_power_report(report_path)
# per_group.to_parquet("result/post_synth_power_by_group.parquet", index=False)