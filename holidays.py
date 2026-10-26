from datetime import date, timedelta
from typing import Tuple

NSE_BSE_HOLIDAYS = {
    '2026-01-26', '2026-03-03', '2026-03-26', '2026-03-31', '2026-04-03',
    '2026-04-14', '2026-05-01', '2026-05-28', '2026-06-26', '2026-08-15',
    '2026-09-14', '2026-10-02', '2026-10-20', '2026-11-08', '2026-11-10',
    '2026-11-24', '2026-12-25',
    '2027-01-26', '2027-03-22', '2027-03-26', '2027-04-14', '2027-05-01',
    '2027-08-15', '2027-10-02', '2027-10-09', '2027-10-29', '2027-12-25'
}

def is_trading_day(dt: date) -> bool:
    if dt.weekday() >= 5:
        return False
    if dt.strftime('%Y-%m-%d') in NSE_BSE_HOLIDAYS:
        return False
    return True

def count_trading_days(start_date: date, end_date: date) -> int:
    if start_date >= end_date:
        return 1
    cur = start_date
    trading_days = 0
    while cur <= end_date:
        if is_trading_day(cur):
            trading_days += 1
        cur += timedelta(days=1)
    return max(1, trading_days)

def get_target_horizon_date(start_date: date, est_trading_days: int) -> Tuple[date, int, int]:
    cur_date = start_date
    completed_trading_days = 0
    skipped_weekends = 0
    skipped_holidays = 0

    while completed_trading_days < est_trading_days:
        cur_date += timedelta(days=1)
        if cur_date.weekday() >= 5:
            skipped_weekends += 1
        elif cur_date.strftime('%Y-%m-%d') in NSE_BSE_HOLIDAYS:
            skipped_holidays += 1
        else:
            completed_trading_days += 1

    return cur_date, skipped_weekends, skipped_holidays
