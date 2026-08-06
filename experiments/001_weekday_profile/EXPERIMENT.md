# 001_weekday_profile

**Hypothesis:** averaging the last 4 same-weekday observations beats pure
seasonal naive by smoothing one-off spikes (campaign days, hiccups), at the
cost of lagging trend by ~2 weeks.

**Expected behavior:** better wMAPE than 000 on noisy mid-size customers;
possibly worse right after level shifts.
