# Process-flow information sufficiency audit

Scope: every process flow tracked in this repo (active profiles plus the planned
SCMOS ladder families), scored against the four-point completeness standard that
`ams_c35` was brought up to:

1. **SPICE model** — MOS compact-model cards, run-matched to the process.
2. **PEX-RC** — sheet resistance, contact/via resistance, and interlayer
   capacitance coefficients from the *same* measured run.
3. **Field stack** — dielectric permittivity/thickness and substrate resistivity
   usable by a field solver (FastCap/FastHenry/Magic style).
4. **Benchmark** — a measured circuit datum (ring oscillator or RF device) for
   end-to-end calibration checks.

Grades: **A** first-hand measured data verified in this repo's evidence set;
**B** derived/partial (e.g. one coefficient family from the run, another from an
aggregate); **C** missing or explicitly withheld.

Source-nature labels used below: `official` = original MOSIS/foundry/PDK text;
`official-mirror` = verbatim copy hosted by a third party; `archive` = archived
original (Wayback); `aggregate` = NCSU CDK tables that merge multiple runs.

## Evidence inventory

All first-hand MOSIS parametric reports for the ladder runs are present locally
in the NCSU CDK mirror and were re-read this session:

| Run | Process | Local file | Verified highlights |
| --- | --- | --- | --- |
| N8BN | AMI C5N 0.5 µm | `…/ncsu-cdk-1.6.0/models/MOSIS_reports/n8bn-params.txt` | Rsh 79.4/108.1/24.7/25.6/0.09/0.09/0.09; cR 51.0/116.0/17.7/17.1/1.58/1.85; RO 121.51 MHz |
| N8AG | HP AMOS14TB 0.5 µm | `…/n8ag-params.txt` | Rsh 2.5/2.0/2.1/0.07/0.07/0.05; cR 2.3/2.0/1.8/0.88/0.36; RO 136.86 MHz |
| N88Z | AMI ABN 0.6 µm | `…/n88z-params.txt` | RO 49.05 MHz |
| N88W | HP GMOS10QA 0.35 µm | `…/n88w-params.txt` | Rsh 3.0/2.3/2.5/0.06/0.06/0.06/0.03; cR 2.7/2.3/2.2/1.01/0.92/0.81; TOX 79 Å; RO 176.09 MHz |
| N88Y | TSMC SCN035H 0.35 µm | `…/n88y-params.txt` | Rsh 79.1/153.4/7.4/47.4/0.07/0.07/0.04 (non-silicided); cR 54.8/118.5/5.6/31.4/1.31/1.42; TOX 76 Å; RO 196.17 MHz |
| N94S | TSMC SCN025 0.25 µm | `…/n94s-params.txt` | Rsh 4.7/3.5/4.2/0.06/0.08/0.08/0.08 + M5 0.03; cR 6.7/5.7/5.7/2.02/4.07/5.79/8.13; TOX 58 Å; **no ring oscillator** |
| N87R | AMI SCN10 1.0 µm | `…/n87r.prm` | Rsh 45.9/63.6/31.9/57.7/0.06/0.05/824; cR 25.8/48.1/19.0/43.1/0.28; TOX 165 Å; RO 110.33 MHz; LEVEL3 + BSIM3 |
| N91W | Orbit SCNA20 2.0 µm | `…/n91w-params.txt` | Rsh 30.1/61.3/21.5/21.6/0.06/0.03/2819; cR 12.2/38.2/7.2/7.3/0.05; TOX 406 Å; RO 36.62/40.24 MHz; LEVEL3 + BSIM3 |

Retrieved this session (was missing):

| Run | Process | Source | Nature |
| --- | --- | --- | --- |
| T28M (LO_EPI) | TSMC SCN018 0.18 µm, DSCN6M018_TSMC | Wayback capture 2004-10-26 of `mosis.com/cgi-bin/params/tsmc-018/t28m_lo_epi-params.txt`; saved verbatim at `docs/mosis_evidence/t28m_lo_epi-params.txt` | `archive` (official original) |

Verified T28M content: Rsh N+ 6.7 / P+ 7.5 / poly 7.8 / silicide-block 349.4 /
M1–M5 0.08 / M6 0.03 / N-well 933; contact N+ 11.2 / P+ 12.2 / poly 10.5 /
via1 5.69 / via2 11.39 / via3 16.73 / via4 21.44 / via5 24.08; TOX 41 Å; full
area/fringe/overlap C table across 6 metals; RO DIV1024 31-stage 1.8 V
428.59 MHz (3.3 V thick-oxide 343.91 MHz); complete BSIM3 NMOS/PMOS cards in the
same file. The `tsmc18d`/`tsmc20` cards shipped by the CDK are runs **T29B** and
**T26X** — T28M's own cards come only from this report.

Also verified: the CDK `publicModel` cards pair to ladder runs as
`hp10N/P → N88W`, `tsmc35N/P → N88Y`, `tsmc25N/P` + `tsmc25dN/P → n94s W08`.

Failed retrievals (attempted, no first-hand result):

- `mosis.com/cgi-bin/params/*` endpoints are dead (connection/SSL failure);
  only Wayback snapshots serve them.
- T28M exact-URL Wayback "available" API reported no snapshot, but the CDX
  wildcard + explicit `20041026191005` fetch succeeded; other T28M snapshots
  exist (2003-05-24, 2003-07-31).
- Scribd document 850317524 (`tsmc350`) is **T27K**, a different TSMC035 run
  (silicided: N+ 3.3 Ω/□), not N88Y. It is an `official-mirror` of the real T27K
  MOSIS file — useful as a silicided cross-check, never as N88Y data.
- N88W/N88Y/N94S/N87R/N91W have no useful public retrieval target beyond the
  local CDK mirror; that mirror is the authoritative copy in scope.

## Field-stack retrieval survey (online, this session)

All MOSIS parametric reports stop at electrical tables; none carry εr / conductor
thickness / substrate resistivity. Online retrieval found first-hand foundry
thickness documents for two ladder families; the rest only have era/paper ranges.

### First-hand foundry documents

**TSMC018 (T28M) — full stack, official.** TSMC document `T-018-MM-SP-001`
Ver. 1.3 (2004, "0.18UM MIXED SIGNAL 1P6M SALICIDE 1.8V/3.3V RF SPICE MODELS",
TSMC-RESTRICTED; third-party hosts: scribd doc 928142601, eetop/iczhiku mirror).
Table 10.1 gives conductor + dielectric parameters:

| Layer | Thickness | k | Notes |
| --- | --- | --- | --- |
| FOX | 3500 Å ±17.1% | 3.9 | distance PO1→substrate 3500 Å |
| ILD | 7500 Å ±21.4% | 4.0 | |
| IMD1a..IMD5a | 11800 Å ±20% | 3.7 | planarized oxide |
| IMD1b..IMD4b | 2000 Å ±3% | 4.2 | |
| IMD5b | 3500 Å ±3% | 4.2 | |
| PASS1/2/3 | 25000/1500/6000 Å ±10% | 4.2/4.2/7.9 | HDP; conformal passivation |
| PO1 (poly) | 2000 Å | | min w 0.18 / sp 0.25 µm |
| M1 | 5300 Å | | min w 0.23 / sp 0.23 µm |
| M2–M5 | 5300 Å | | min w 0.28 / sp 0.28 µm |
| M6 (thick) | 23400 Å | | min w 1.50 / sp 1.50 µm |

Both stacks above are archived in this repo:
`docs/mosis_evidence/t018mms001_table10-1.md` and
`docs/mosis_evidence/tsmc035_cross_section.md` (with provenance and caveats).

Consistent with a 2007 IEEE MTT paper that models 0.18 µm 1P6M as M1–M5 0.55 µm /
top 2.0 µm. T28M is DSCN6M018 (6-metal SCN018, 2001 run); this 2004 spec is the
closest official 6M stack and matches its M1–M5 0.08 / M6 0.03 Ω/□ sheet pattern.
Substrate resistivity not stated in the doc (node-typical ~10 Ω·cm in RF papers).

**TSMC035 (N88Y) — thickness cross-section, official rules.** "TSMC035um
Thickness Rule" (TSMC 0.35um design rules, third-party-hosted PPT on scribd
363796096) gives the 4M cross-section: GOX 0.0078 µm; thick oxide (poly→M1)
1.09 µm; M1 0.67 µm; Via1/Oxide2 (M1→M2) 1.1 µm; M2 0.64 µm; Via2/Oxide3
1.1 µm; M3 0.64 µm; Via3/Oxide4 1.1 µm; M4 0.925 µm; total 7.275 µm. GOX 78 Å
matches T27K's 78 Å and is consistent with N88Y's 76 Å (run-to-run). k not stated
→ use SiO2 3.9. N88Y is a **3-metal** run (report has MTL1–3, M3=0.04 Ω/□);
map M1 0.67 / M2 0.64 / M3(top, thick-metal tier) 0.925 µm [INFERENCE: 3M top
metal falls in the 4M M4 class].

**Cross-reference:** AMS C35 (`ENG-182`, the ams_c35 stack source) is the same
0.35 µm generation; its M1 0.665 µm / IMD1 1.0 µm agree numerically with the
TSMC035 figures, strengthening both (no licensing relationship asserted).

### Paper ranges only (no first-hand foundry thickness)

| Flow | What is public | Match check |
| --- | --- | --- |
| TSMC025 (N94S) | M1 0.4–0.5 µm, M2–M4 ~0.6 µm, M5 (top) 0.8–1.0 µm, ILD 0.6–0.9 µm, GOX 55–60 Å, STI, p-sub 1–20 Ω·cm | GOX range matches N94S 58 Å |
| HP035 (N88W) | M1 0.4–0.6 µm, ILD 0.8–1.2 µm, 4M with thick top tier | consistent with N88W sheet pattern (M1–3 0.06, M4 0.03 Ω/□) |
| HP05 (N8AG) | M1 0.6–0.7, M2 0.6–0.8, M3 (top) 1.0–1.2 µm; IMD 0.8–1.2 µm; poly 0.25–0.4 µm; FOX 0.4–0.6 µm | consistent with N8AG sheet pattern (M1–2 0.07, M3 0.05 Ω/□) |
| AMI05 C5N (N8BN) | poly 0.4 µm + glass 3.2 µm (NIST J. Res. 111(3), thermal model); TOX 141 Å (NIST-cited iastate lot report = N8BN report's own TOX); no metal/IMD/FOX; C5X Rev T metalization table login-walled | TOX cross-validated at run level |
| AMI12 ABN (N88Z) / AMI16 (T1AZ) | process identity only (EE Times 1992: ABN = 1.2 µm double-poly/double-metal) | — |
| AMI10 CWL (N87R) | process identity only (EE Times 1992: CWL = 0.8 µm single-poly/double-metal + poly-cap) | — |
| Orbit 2.0 (N91W) | FOX 0.6–0.8 µm, poly 0.35–0.45 µm, M1 0.5–0.6 µm, M2 0.8–1.0 µm, GOX 400–500 Å | GOX range matches N91W 406 Å; classic MOSIS 2 µm LEVEL2 card TOX 40 nm matches |

Full search log with every source checked: `docs/mosis_evidence/ami_hp_field_search.md`.

### Derived-stack policy (flows without first-hand thickness)

Same rule as `cnm25`/`ams_c35`: build the stack from era-typical ranges above,
mark every entry `derived`, and use the run's own measured C table as a
consistency constraint (M1 area-C-to-substrate ÷ implied ILD height → effective
εr; if the result strays outside 3.5–4.2, the assumed height is wrong). Substrate
ρ: node-typical 5–20 Ω·cm unless a run document states otherwise (none do);
TSMC018 ~10, TSMC035 ~15 Ω·cm [paper-derived, not foundry-stated]. These stacks
are clearly labeled derived in any generated profile and never presented as
foundry signoff data.

## Per-process audit

| Flow | Profile | MOS run / source | 1 SPICE | 2 PEX-RC | 3 Field stack | 4 Benchmark | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AMI 0.5 µm | ami06 | N8BN | A | B | C | A | **B** |
| HP 0.5 µm | hp06 | N8AG | A | B | C | A | **B** |
| AMI 0.6 µm | ami16 | N88Z | A | A | C | A | **A−** |
| CNM25 2.5 µm | cnm25 | IMB-CNM APDK | A | B | B | C | **B** |
| ams 0.35 µm | ams_c35 | ENG-182/188 | A | A | A | B | **A** (gold standard) |
| HP 0.35 µm | (planned hp10) | N88W | A | A | C | A | **A−** |
| TSMC 0.35 µm | (planned tsmc035) | N88Y | A | A | B | A | **A−** |
| TSMC 0.25 µm | (planned tsmc025) | N94S | A | A | C | C | **B+** |
| TSMC 0.18 µm | (planned tsmc018) | T28M | A | A | B | A | **A−** |
| AMI CWL 1.0 µm | (planned amcwl) | N87R | A | A | C | A | **A−** |
| Orbit 2.0 µm | (planned orbit) | N91W | A | A | C | A | **A−** |
| LS1u | ls1u | academic/empirical | B | C | C | C | **C** (documented limit) |
| OpenRule1um | openrule1um | measured primitive contract | B | C | C | C | **C** |

## Findings

### 1. PEX-RC is run-complete for every MOSIS ladder family; two active profiles lag

All nine MOSIS reports carry full sheet/contact/via **and** area/fringe/overlap
C tables from the same lot. `ami16` already consumes its report end-to-end.
`ami06` and `hp06` still declare `capacitance_source: NCSU CDK layerDefinitions.tf
/ divaMultiLevel.il` (an `aggregate`, e.g. HP sheet values there cite N98R/N74K)
and explicitly withhold junction/substrate C. The report C tables (N8BN: M1/M2/M3
area 36/21/12, perim 77/50/55; N8AG: area 28/13/9, overlap 319/324) are not yet
in the manifests. This is the highest-value mechanical upgrade available: switch
ami06/hp06 C and sheet coefficients to N8BN/N8AG, following the ami16 pattern.
Sheet deltas to reconcile when doing so (CDK manifest vs report): ami06 poly
25 vs 24.7, poly2 26 vs 25.6, M3 0.05 vs 0.09 (nwell 819 matches); hp06 poly
2.0 vs 2.1, M1/M2/M3 match at 0.07/0.07/0.05, nwell 728 has no report value
(N8AG does not publish a well sheet row).

### 2. Field stack: still the widest gap — but TSMC018/TSMC035 now have first-hand thickness

No MOSIS parametric report ships εr / conductor thickness / substrate ρ. Online
retrieval (this session) found first-hand foundry documents for two of the nine
ladder families: TSMC018 (`T-018-MM-SP-001` Table 10.1: full 6M conductor +
per-layer k/thickness) and TSMC035 (design-rules cross-section: M1 0.67 / M2–3
0.64 / M4 0.925 µm, ILD tiers 1.1 µm). Both also agree with the AMS C35
ENG-182 figures for the shared 0.35 µm generation. The remaining seven families
have only paper/era ranges, so their stacks must be built `derived` with the
run's measured C table as a consistency constraint (see survey section). The
measured C densities (aF/µm²) constrain the ILD `εr/t` products implicitly for
every family, so a derived stack is always checkable, but it is not first-hand.
`ams_c35` remains the only flow with a complete first-hand stack (εr/t/substrate
all from ENG-182).

### 3. N88Y is non-silicided; T27K is a different TSMC035 run

N88Y (TSMC SCN035H): N+ 79.1 Ω/□, contact N+ 54.8 Ω — no silicide. T27K (also
SCN035H): N+ 3.3 Ω/□ — silicided, plus a full second TSMC035 dataset with its own
RO (163.36 MHz). Both are first-hand TSMC035 evidence, but they must stay in
separate profile variants; the `tsmc35N/P` model cards pair to **N88Y**, so the
planned TSMC035 profile uses N88Y coefficients. T27K may be recorded as a
silicided cross-check variant only.

### 4. N94S has no ring oscillator — benchmark substitute required

The N94S report ends at the C table; no RO section exists (grep for MHz/RO
returns zero). For the planned TSMC025 profile the benchmark column must be
"absent from report". The SUBM-vs-DEEP experiment can still be validated with an
inverter-chain transient under ngspice (same method used for ams_c35/cnm25),
which compares logic-stage delay rather than a measured RO frequency. Mark the
profile benchmark as derived, not first-hand.

### 5. T28M pairing is now complete from one file

The CDK ships `tsmc18d`/`tsmc20` = T29B/T26X, so T28M previously had a MOS/RC
mismatch. The archived T28M report contains its own BSIM3 cards, so MOS + PEX-RC
+ RO all come from the single first-hand file. This removes the "needs MOS/RC
re-pairing" blocker from the ladder table.

### 6. LS1u / OpenRule1um are intentionally insufficient

LS1u has no measured process; its PEX is `scmos_legacy` explicitly not calibrated
to the process. OpenRule1um's SPICE is a measured primitive contract without
canonical bindings, and PEX is deferred. These are documented limits, not gaps to
retrieve.

## Next actions (by value)

1. Upgrade `ami06`/`hp06` PEX manifests to N8BN/N8AG sheet+C (ami16 pattern);
   regenerate techs; re-run `test_stdcell_spice_pex.py`.
2. Build `profiles/hp10/` from N88W (first complete planned family: report +
   matching hp10N/P cards + RO); field stack derived from era ranges.
3. Build TSMC035 from N88Y (separate T27K silicided variant if wanted) with the
   official TSMC035 cross-section as its first-hand thickness.
4. Build TSMC025 from N94S with a derived inverter-chain benchmark; field stack
   derived from paper ranges, cross-checked against the N94S C table.
5. Build TSMC018 from T28M using `docs/mosis_evidence/t28m_lo_epi-params.txt`;
   field stack from `T-018-MM-SP-001` Table 10.1.
6. For each planned profile, add a field stack with explicit `official` /
   `derived` labeling and its assumption chain; keep `pex_runtime=false` (no
   Magic backend yet) exactly as cnm25/ams_c35.
