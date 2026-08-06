# 000_seasonal_naive

**Hypothesis:** none — this is the floor. Repeat last observed same weekday
(t-7, falling back to t-14 for leads 8–14).

**Expected behavior:** decent on stable weekly rhythms, blind to trend,
holidays, campaigns and churn. Every real experiment must beat this.
