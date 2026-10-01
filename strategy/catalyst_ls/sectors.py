"""Map SEC SIC codes to broad sectors (GICS-like) so rules can be sector-specific."""
from __future__ import annotations

# (low, high, sector), checked in order, so narrower ranges come first.
_RANGES = [
    (1220, 1229, "Energy"), (1300, 1399, "Energy"), (2900, 2999, "Energy"),
    (5170, 5172, "Energy"),
    (2830, 2836, "Healthcare"), (3840, 3851, "Healthcare"), (5122, 5122, "Healthcare"),
    (8000, 8099, "Healthcare"), (8731, 8731, "Healthcare"),
    (2840, 2844, "Consumer Staples"), (5140, 5149, "Consumer Staples"), (5400, 5499, "Consumer Staples"),
    (5912, 5912, "Consumer Staples"),
    (3570, 3579, "Technology"), (3630, 3639, "Consumer Discretionary"), (3600, 3699, "Technology"),
    (3820, 3829, "Technology"), (3861, 3861, "Technology"), (7370, 7379, "Technology"),
    (3711, 3716, "Consumer Discretionary"), (3751, 3751, "Consumer Discretionary"),
    (7310, 7319, "Communication"), (2700, 2799, "Communication"), (4800, 4899, "Communication"),
    (7800, 7899, "Communication"),
    (4950, 4959, "Industrials"), (4900, 4999, "Utilities"),
    (6770, 6770, None),  # blank-check companies (SPACs)
    (6500, 6553, "Real Estate"), (6798, 6798, "Real Estate"), (6000, 6799, "Financials"),
    (100, 999, "Consumer Staples"), (2000, 2199, "Consumer Staples"),
    (1000, 1499, "Materials"), (2400, 2499, "Materials"), (2600, 2699, "Materials"),
    (2800, 2899, "Materials"), (3000, 3099, "Materials"), (3200, 3399, "Materials"),
    (2200, 2399, "Consumer Discretionary"), (2500, 2599, "Consumer Discretionary"),
    (3100, 3199, "Consumer Discretionary"), (3900, 3999, "Consumer Discretionary"),
    (5200, 5999, "Consumer Discretionary"), (7000, 7099, "Consumer Discretionary"),
    (7200, 7299, "Consumer Discretionary"), (7500, 7599, "Consumer Discretionary"),
    (7900, 7999, "Consumer Discretionary"),
    (1500, 1799, "Industrials"), (3400, 3599, "Industrials"), (3700, 3899, "Industrials"),
    (4000, 4799, "Industrials"), (5000, 5199, "Industrials"), (7300, 7399, "Industrials"),
    (8100, 8999, "Industrials"),
]

# Lenders and BNPL names whose SIC code files them under business services.
OVERRIDES = {"AFRM": "Financials", "SEZL": "Financials", "UPST": "Financials", "SOFI": "Financials"}


def sector_for(sic: str | int | None, ticker: str | None = None) -> str | None:
    if ticker and ticker.upper() in OVERRIDES:
        return OVERRIDES[ticker.upper()]
    try:
        code = int(sic)
    except (TypeError, ValueError):
        return None
    for low, high, sector in _RANGES:
        if low <= code <= high:
            return sector
    return None
