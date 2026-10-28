# Decision log: Darukaa Adaptive v1.1.0

This folder holds the approved methodology and process decisions. Read it before changing any code. Each decision has an ID, a date, who approved it, the evidence behind it, its status, and the decisions that supersede it or that it supersedes.

**Source labels used throughout:**
- **[STD]**: a standard or framework, such as Nature Positive State of Nature, TNFD, SBTN, ESRS E4, SEEA-EA or Plan Vivo.
- **[VENDOR]**: a vendor or tool approach.
- **[DARUKAA]**: Darukaa's own evidence, such as audits, runs and decisions.

**Evidence levels:**
- static reading
- unit test
- mock
- real Earth Engine (EE) run
- end-to-end Colab run

| File | Content |
|---|---|
| `2026-10-16_phase1_decisions.md` | The 14 decisions from the Phase 1 audit, re-verified on 23 Oct, with the current status of each |
| `2026-10-22_plan_decisions.md` | Reporting-scale and managed-land decisions from the one-week plan |
| `2026-10-23_decisions.md` | Method approval, pillar restructure, assessment units, pressure scoring, headline rule |
| `2026-10-25_decisions.md` | Pressure reference (option B, without circularity) and peak-window buffer, after the first live run |
| `2026-10-26_decisions.md` | Low-pressure reference floor and search widening; fire-year validity |
| `2026-10-27_decisions.md` | Canopy-height source switch to CHMv2 (when readable in Earth Engine); headline option C; SoN composite score (D-27-3) |
| `2026-10-28_decisions.md` | Canopy-height evidence rules (D-28-1); preparatory species metrics for P3 (D-28-2); CHMv2 parked (D-28-3) |
| `audit-2026-10.md` | Keep, change or delete verdict for each file, plus the batch log |

**Process rules** (approved 23 Oct):
- **Scientific changes:** propose them first, then wait for Gaurav's approval.
- **Mechanical changes** covered by an approved decision are made in small batches. Each batch goes in this order:
  1. Write the tests.
  2. Implement the change.
  3. Run the offline tests.
  4. Commit as Gaurav Singh to `main`, with no co-author line.
  5. Update `audit-2026-10.md`.
