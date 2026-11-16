# Numerical precision clarification after software review

The protocol and 32 selected cases are unchanged. Before recording the final
comparison report, software review found a parameter-conversion counterexample:
chi-square df `999999.00000000005`, statistic `999999.000000000000000000` and
reported p `0.49981193670938`. An independent 80-digit upper-gamma calculation
gives p approximately `0.49981193670937693334895`, inside the printed interval.
Casting df to float loses the fractional part and could falsely refute the p.
The existing probability ULP margin did not bound parameter-conversion error.

The implementation therefore abstains when a declared exact decimal df cannot
be represented exactly by the float backend. This includes ordinary nonbinary
decimals such as 1.3, not only very long inputs. Exactly representable positive
fractional df, such as .5 or 10.5, remain supported. This conservative guard does
not claim general df-uncertainty propagation or arbitrary-precision inference.
Statistic rounding interval endpoints are converted outward, using adjacent
floats when necessary, rather than silently collapsing a narrow decimal range.
Backend probability accuracy remains numerical, not a formal error-bound proof.

Regression/analytic tests cover this clarification separately. No selected case,
historical reference label or original 0.9.0 result was changed; no NIST-derived
score was optimized. The clarification hash is recorded in the comparison.
