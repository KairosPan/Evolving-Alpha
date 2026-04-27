"""Generate a deterministic synthetic dataset for one trading day."""
from __future__ import annotations

import pandas as pd


def build_warming_day(date: str = "2026-04-25") -> dict:
    ztb_today = pd.DataFrame({
        "代码":         ["600202", "002438", "300999", "600988"],
        "名称":         ["中核科技", "江苏神通", "新票", "赤峰黄金"],
        "连板数":       [3, 2, 1, 1],
        "封单金额":     [3e8, 1e8, 0.5e8, 0.6e8],
        "首次封板时间": ["09:30", "10:00", "10:30", "09:50"],
        "炸板次数":     [0, 0, 1, 0],
        "所属行业":     ["核能", "核能", "其他", "黄金"],
        "上市天数":     [800, 600, 1000, 700],
        "开盘价":       [10.0, 8.0, 5.0, 6.0],
        "涨停价":       [11.0, 8.8, 5.5, 6.6],
    })
    ztb_yest = pd.DataFrame({
        "代码":         ["600202", "600988"],
        "名称":         ["中核科技", "赤峰黄金"],
        "连板数":       [2, 1],
        "封单金额":     [2e8, 0.5e8],
        "首次封板时间": ["09:40", "10:30"],
        "炸板次数":     [0, 1],
        "上市天数":     [800, 700],
        "开盘价":       [9.5, 5.5],
        "涨停价":       [10.0, 6.0],
    })
    activity = pd.DataFrame([
        {"date": f"2026-04-{d:02d}", "red_count": rc}
        for d, rc in zip(range(15, 26),
                         [1100, 1200, 1300, 1400, 1500, 1600, 1700, 1800, 1900, 2000, 2100])
    ])
    idx_sh = pd.DataFrame({
        "close":  [3000 + i for i in range(100)],
        "amount": [1e10] * 100,
    })
    return {
        "ztb_today": ztb_today, "ztb_yesterday": ztb_yest,
        "blast": pd.DataFrame(),
        "idx_sh": idx_sh, "idx_cyb": idx_sh,
        "activity": activity,
    }
