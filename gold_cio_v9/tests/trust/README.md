# Tester Trust Gate

Gold CIO v9.1 treats all EXP-0001 outputs as diagnostic-only until the tester itself is trusted.

The gate is green only when all required tests pass:
1. known-answer verdict behavior,
2. PIT leakage and purge integrity,
3. deterministic replay,
4. trials-registry integrity,
5. config immutability.

Important: a green workflow is not a hard merge barrier unless GitHub branch protection/rulesets mark `Tester Trust Gate` as a required status check. That repository setting must be enabled after the first stable green run.
