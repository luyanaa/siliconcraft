# D35 (TSMC 0.35 µm Mixed-Signal 2P4M Polycide 3.3/5 V) — SUBM/DEEP audit

Point-by-point audit of the TSRI **D35** process against its historical MOSIS
**SCMOS** lineage, plus the PEX and SPICE collateral implemented for it in this
repository.

Companion implementation: `profiles/tsmc035_4m2p/` (new profile),
`common/pex/wat_rc.py`, `scripts/run_wat_pex.py`, `scripts/test_tsmc035_pex.py`.

Evidence files:
[`d35_scmos_layer_map.md`](mosis_evidence/d35_scmos_layer_map.md),
[`d35_wat_pex_data.md`](mosis_evidence/d35_wat_pex_data.md),
[`d35_physical_stack.md`](mosis_evidence/d35_physical_stack.md),
[`tsmc035_cross_section.md`](mosis_evidence/tsmc035_cross_section.md).

---

## 0. Verification-environment limitation (material to every claim below)

The requester supplied external URLs (university theses reproducing official
MOSIS WAT reports, a patent, a journal paper, MOSIS SCMOS documentation). **The
port was produced in a sandbox with no working network egress:**

* `web_search` → `DeepSeek API error (HTTP 402): Insufficient balance`
* `web_fetch` → `URL hostname resolves to a non-public IP address`
* no field solver (FastCap / FasterCap / Palace) is installed, so PEX v1 is
  delivered as a validated solver **input**, never as a solved result (§2.14)

Therefore this audit distinguishes three evidence classes, and marks them
explicitly everywhere:

| class | meaning |
|---|---|
| **local_first_hand** | read directly from a file present in this environment (NCSU CDK 1.6.0, repository docs). Verified. |
| **external_reported** | supplied by citation; **not** re-fetched or independently re-read. Tagged `not_reverified_offline`. |
| **repo_derived** | computed or inferred in this port from the above. |

Where an external quantity overlaps a local first-hand quantity, it was
**cross-checked numerically** rather than merely quoted (§6). That cross-check is
the substantive evidence this port contributes; it does not upgrade the external
documents to verified status.

---

## 1. Verdict summary

| dimension | verdict | basis |
|---|---|---|
| Logical ontology (layer/device/process identity) | **HIGH** | CDK `globalData.il` + techfile + stream map, read locally |
| Historical GDS submission map | **HIGH** | `pipo/streamInLayermap`, matches the proposed map exactly (§5) |
| Historical SCN4ME match | **HIGH** | CDK `mosisCode SCN4ME_SUBM`; WAT cross-check within ~10 % CBEOL (§6) |
| Current TSRI direct map | **UNKNOWN** | the licensed TSRI/CIC stream map and runset were not available |
| Tapeout authority | **NO** | no foundry QRC table, no current runset, historical WAT only |
| SUBM vs DEEP | **D35 is SUBM only — no 0.35 DEEP exists** | §4 |
| SPICE models | local first-hand, simulatable (nominal only) | shipped `tsmc35N/P` = MOSIS run N88Y |
| PEX | research: analytical WAT RC (v0) + reconstructed field solver (v1) | neither is signoff |

**The premise "2002/2005 WAT numbers must not be claimed as 2026 D35 signoff
parameters" is correct and is now enforced in code**, not just documented: every
PEX report carries `calibrated_to_current_d35: false` and `signoff: false`, and a
coefficient set is labelled with its actual verification status: the locally
verified ones report `verified_local_report` or `verified_local_techfile`, and
everything else reports `external_unverified` (§8).

---

## 2. Point-by-point analysis

### 2.1 Is D35 the TSMC 0.35 µm Mixed-Signal 2P4M Polycide 3.3/5 V process?

**Yes — verified locally.** The NCSU CDK 1.6.0 records
`NCSU_techData["TSMC_CMOS035_4M2P"]` as:

* description `TSMC 0.35um (0.4um drawn) (4M/2P option)`
* techfile `tsmc_04_4m2p.tf`, techlib `NCSU_TechLib_tsmc04_4M2P`
* `mosisCode SCN4ME_SUBM`
* lambda 0.2, minL 0.4, minW 0.6, gridRes 0.1
* `fetModelPrefix tsmc35`

and `techfile/tsmc_04_4m2p.tf` sets `metal3Available`, `metal4Available`,
`elecAvailable`, `hvAvailable` all `t`. Four metals, two polys, a polycide gate
stack (poly sheet 7.4 Ω/□, i.e. polycided), a 3.3 V core and a thick-oxide
(tactive) path for the higher-voltage class — matching the marketing name
component for component. The name "Polycide" is independently consistent with
the measured poly sheet resistance: poly1 is 7.4 Ω/□ (polycided) while poly2 is
47.4 Ω/□ (not polycided).

The equivalence of the TSRI name to this CDK entry is a **documented lineage
claim**, not a fetched statement: no TSRI document was reachable offline. What is
locally verified is the *CDK* identity; what is asserted is that D35 names the
same process.

### 2.2 Lineage with MOSIS SCN035 / SCN4ME (λ = 0.20 µm)

**Confirmed.** `mosisCode SCN4ME_SUBM` with λ = 0.2 µm is exactly the
submicron SCMOS ladder entry. The naming decomposes as
`SCN` + `4` metals + `M` mixed-signal + `E` epi + `_SUBM` submicron.

Additional independent support found locally: the **N88Y MOSIS report is itself
tagged `COMMENTS: SMSCN3ME04`** — i.e. the mixed-signal epi option family
(SCN3ME). The 3-metal mixed-signal epi option and the 4-metal
`SCN4ME_SUBM` option are successive members of the same SCMOS mixed-signal epi
line, which is precisely the lineage the premise asserts.

Note the repository already declares `tsmc035_4m2p` and `tsmc035_4m2` in
`schema/scmos_process_matrix.yaml` (with `rule_family scmos_subm`), so the
process matrix anticipated this profile; what
was missing was the materialised profile itself (§9).

### 2.3 "BEOL / basic-CMOS abstraction highly related"

**Agreed, and now quantified.** The 0.35 µm generation's CBEOL abstractions are
close enough that the local 3-metal N88Y coefficients predict the 4-metal MM_EPI
coefficients within ~10 %:

* M1–M2 coupling area 36 vs 38 aF/µm² (+5.6 %); fringe 56 vs 58 aF/µm (+3.6 %)
* M1–M3 coupling area 13 vs 14 (+7.7 %); fringe 35 vs 37 (+5.7 %)
* M2–M3 coupling area 36 vs 39 (+8.3 %); fringe 53 vs 53 (0.0 %)
* M1/M2 sheet resistance identical (0.07 Ω/□ both)
* N+/P+ active sheet resistance within 0.4 %

The abstraction is "highly related" in the CBEOL and FEOL-active sense. It is
**not** identical: poly sheet resistance differs by 17.6 % and contact resistance
by 12–29 % between the two runs (§6), which is real lot-to-lot and
option-to-option spread.

### 2.4 SUBM vs DEEP — the central audit question

**Finding: there is no TSMC 0.35 µm DEEP option. D35 is a SUBM process, and
labelling it DEEP would be incorrect.**

Evidence:

1. The repository defines the family by identifier: `common/process_ir.py`
   computes `is_deep = any("DEEP" in identifier.upper() ...)` over
   `meta.process` and `meta.mosis_code`, and enforces a biconditional —
   `scmos_deep` **requires** a DEEP identifier, and a DEEP identifier
   **requires** `scmos_deep`. Our identifiers are `TSMC_CMOS035_4M2P` /
   `SCN4ME_SUBM`; neither contains `DEEP`, so the profile must be `scmos_subm`.
   This is enforced, not merely conventional: the profile is rejected otherwise.
2. The CDK's 0.35 entries are `TSMC_CMOS035_4M2P` (`SCN4ME_SUBM`),
   `TSMC_CMOS035_4M` (`SCN4M_SUBM`) and the inactive
   `TSMC_CMOS035_3M2P` (`SCN3ME_SUBM`). **All three are `_SUBM`. None is
   `_DEEP`.**
3. `scmos_deep` in this repository is used by the 0.25 µm and 0.18 µm entries
   (MOSIS `SCN5M_DEEP` / `SCN6M_DEEP` class) — a different generation and a
   different MOSIS rule set.

Consequence for the port: `meta.rule_family = scmos_subm`, and the reference
DRC/LVS decks are driven with `RULE_FAMILY=scmos_subm`, `LAMBDA=0.20`. Any
attempt to port D35 as `scmos_deep` would be rejected by the IR contract and
would be factually wrong.

*(If the requester's "DEEP" refers to the TSRI-internal naming for a
deep-submicron rule set rather than the MOSIS DEEP ladder, that is a distinct
claim that needs a TSRI document — which was not reachable offline. Recorded as
an open question in §11.)*

### 2.5 GDS layer map — the proposed map is exactly right

The proposed map was checked entry by entry against the generated
`layers.yaml` (parsed from the CDK). **All 17 anchors match exactly:**

| proposed | verified | layer |
|---|---|---|
| Nwell 42 | 42 | nwell |
| Active 43 | 43 | active |
| Pselect 44 | 44 | pselect |
| Nselect 45 | 45 | nselect |
| Poly1 46 | 46 | poly |
| Poly2/Electrode 56 | 56 | elec |
| Contact 25 | 25 (+47/48/55) | cc |
| M1 49 | 49 | metal1 |
| Via1 50 | 50 | via |
| M2 51 | 51 | metal2 |
| Via2 61 | 61 | via2 |
| M3 62 | 62 | metal3 |
| Via3 30 | 30 | via3 |
| M4 31 | 31 | metal4 |
| ThickActive 60 | 60 | tactive |
| Glass 52 | 52 | glass |
| PAD 26 | 26 | pad (non-fab annotation) |

Details in [`d35_scmos_layer_map.md`](mosis_evidence/d35_scmos_layer_map.md).

### 2.6 `datatype 0` is a convention, not MOSIS-official

**Agreed, and encoded that way.** MOSIS SCMOS documentation defines GDS *layer
numbers*; the CDK stream map records layer/datatype `0` for every drawing layer,
and no public drawing/pin/label/net datatype matrix was recovered. The profile
therefore declares:

```yaml
gds_policy:
  datatype: {value: 0, authority: siliconcraft_convention}
  purpose_matrix: {status: unavailable}
```

rather than presenting datatype 0 as an official MOSIS purpose matrix.

### 2.7 Contact aliases 47 / 48 / 55

**Confirmed as input aliases, not separate cuts.** `pipo/streamInLayermap`
assigns all four numbers to the single Cadence layer `cc`:

```
cc  drawing  25 0
cc  drawing  47 0
cc  drawing  48 0
cc  drawing  55 0
```

The profile keeps `cc: [25, 47, 48, 55]` and records the aliases with
`physical_cut: false`. Geometry on any of them is a contact cut.

### 2.8 `tactive` / THICK_ACTIVE (GDS 60) and the 5 V HV path

**Layer retained; HV devices deliberately withheld.** The CDK Diva deck quotes
MOSIS FAQ 4.0 verbatim:

> "Active overlapped by Thick_Active will have the thicker gate oxide.
> Thick_Active by itself does nothing."

and enforces `geomOutside(tactive, active)` → "Thick-active without active does
nothing" under `hvAvailable`. `hvAvailable` is `t` for this option, and the
reference DRC/LVS decks already recognise HV classes
(`nmos_hv`/`pmos_hv` via `tactive`-derived markers,
`common/drc/scmos_layers.py`; `hvnChannelTran`/`hvpChannelTran`,
`common/lvs/scmos_reference_lvs.py`).

What is missing is a **numerical TSMC 0.35 HV compact model**. None was recovered
locally or from the citations, so the profile binds no HV device and records
`tsmc035_hv` as `representation: contract_only`, `simulator: null`. The layer and
the recognition path exist; the model does not. This is the honest state — the
alternative (guessing an HV card) is explicitly forbidden by repository policy.

### 2.9 `elec` / POLY2 (GDS 56) — capacitor, not transistor

**Confirmed from the CDK deck**, which quotes the 1999-03-01 MOSIS news item:

> "The AMI C5N poly2 can be used to build capacitors in a style identical to
> SCNE (as for AMI 1.2u, Orbit 2u and **TSMC 0.35u**), but not transistors (same
> as TSMC 0.35u)."

and adds a TSMC-0.4 µm-specific check that active and elec may not overlap
(DBM Rule 4.0, applied only for `TSMC_CMOS035_4M2P`/`_3M2P`). POLY2 is therefore
a capacitor/electrode layer; the profile records `tsmc035_poly2_cap` as
`contract_only` and binds no poly2 device.

### 2.10 WAT sheet resistance, contacts and vias

Full tables in [`d35_wat_pex_data.md`](mosis_evidence/d35_wat_pex_data.md) §1.2,
§2 and §4. Key points:

* The local N88Y report gives N+ 79.1, P+ 153.4, poly 7.4, poly2 47.4,
  M1 0.07, M2 0.07, M3 0.04 Ω/□, N-well 1011 Ω/□; contacts 54.8 / 118.5 / 5.6 /
  31.4 Ω; vias 1.31 / 1.42 Ω; gate oxide 76 Å; a 31-stage ring oscillator at
  196.17 MHz / 5.83 µW/MHz/gate.
* **A second local first-hand source exists and is native to the 4M/2P option:**
  the NCSU CDK `techfile/layerDefinitions.tf` block for `TSMC_CMOS035_4M2P`
  (run **T02F**, 2000-05-17; the block itself is labelled "TSMC035 0.35um
  (4M/2P option)"). It gives poly 8.5, N-well 1048, M1/M2/M3 0.07, M4 0.04 Ω/□;
  `ca`/`ce`/`cp` 118.0/6.8/6.8 Ω; via/via2/via3 1.50/1.27/1.16 Ω; and a complete
  4-metal coupling matrix (M1–M2 36/52, M1–M3 14/38, M1–M4 9/28, M2–M3 38/58,
  M2–M4 14/37, M3–M4 34/55). Against N88Y it agrees **exactly** on metal sheet
  resistance and within ~10 % on coupling, while poly sheet (14.9 %) and poly
  contact (21.4 %) show lot-to-lot spread — the same pattern seen against T2AF.
  It is a Cadence techfile, not a WAT report, so it has no device rows and no
  n⁺/p⁺ split; where the model needs those it borrows them from N88Y with
  per-quantity provenance recorded (`per_quantity_provenance.borrowed`).
  It is the **default 4-metal D35 reference**.
* The reported T2AF MM_EPI values agree on M1/M2 (0.07 both), poly2 (−0.6 %),
  N-well (−1.1 %) and N+/P+ active (+0.4 %), and differ on poly (+17.6 %) and
  contacts (+12 to +29 %).
* **Top-metal tier mapping:** N88Y's 3-metal top tier (MTL3 = 0.04 Ω/□) equals the
  4-metal option's M4 (0.04 Ω/□) — now confirmed against **both** the local T02F
  techfile and external T2AF/T59N — while N88Y M1/M2 (0.07) equal T2AF/T59N
  M1/M2/M3 (0.07). This independently corroborates the official cross-section,
  in which M4 (0.925 µm) is the thick tier.

### 2.11 Capacitance matrix

The reported MM_EPI 4-metal coupling matrix (M1–M2 38/58, M1–M3 14/37,
M1–M4 9/29, M2–M3 39/53, M2–M4 14/38, M3–M4 39/65) agrees with the local N88Y
3-metal matrix on the three overlapping pairs within ~8 % (§6).

The 4-metal-only pairs (M1–M4, M2–M4, M3–M4) have no counterpart in N88Y — it is
a 3-metal run — but they **do** have a local counterpart in the T02F techfile
(9/28, 14/37, 34/55). T02F's values sit inside the same spread as T2AF/T19P
(T2AF 9/29, 14/38, 39/65; T19P 9/27, 14/35, 36/59) and are now the default
source for those pairs, so the 4-metal top-tier capacitance no longer rests on
`external_reported` data alone.

### 2.12 LO_EPI vs MM_EPI — a likely silicide confound (open question)

The reported LO_EPI (T19P) N+ ≈ 3.6 Ω/□ and P+ ≈ 2.7 Ω/□ versus MM_EPI/N88Y
≈ 79 / 154 Ω/□ is a ~22× gap. That is far too large to be an epi-resistivity
effect on source/drain sheet resistance, which is dominated by the
junction/silicide stack. A **silicided** source/drain (single-digit Ω/□) versus
**non-silicided** (tens of Ω/□) is the natural explanation, and this repository's
own process audit already separates the non-silicided N88Y run from the silicided
T27K run (N+ 3.3 Ω/□) on exactly that basis.

**Conclusion:** the LO_EPI/MM_EPI distinction as reported is confounded with
silicide/no-silicide. Recorded as an **open question**, not resolved. Practical
consequences implemented: the two classes are kept in separate coefficient sets
with a `capability_separation.rule` forbidding blending, and the default D35
4-metal reference is the **local first-hand T02F 4M/2P techfile**, not an epi
option at all (matching "mixed-signal, 4-metal, 2-poly").

### 2.13 SPICE model cards

* **Local first-hand and simulatable:** `tsmc35N` / `tsmc35P` as shipped by the
  CDK (`models/hspice/public/publicModel/tsmc35N,P`). Their header reads
  `* run N88Y`; `TOX = 7.6E-9` matches the N88Y report's 76 Å, and
  `VTH0 = 0.4964448` (N) is consistent with the report's min-geometry
  Vth 0.54 V. The cards are BSIM3v3.1 (`LEVEL = 49`, `VERSION = 3.1`) with
  `CAPMOD = 2`, `CGDO = CGSO = 2.307E-10`, `CJ = 1.420282E-3`,
  `CJSW = 4.773605E-10`.
* Materialised into `profiles/tsmc035_4m2p/models/tsmc035_4m2p.lib` (single
  section `tsmc035_4m2p`), generated by the generic `scripts/gen_models.py`.
  **The CDK ships no corner directories for the `tsmc35` prefix**, so only the
  nominal section exists — a corner pack is a blocker for production use.
* **Historical reference only:** the reported MM_EPI/LO_EPI BSIM3 cards are
  recorded as `tsmc035_mosis_mm_epi_reference` with
  `calibrated_to_current_d35: false`.
* The N88Y run is **3-metal, non-silicided**. It is FEOL-representative of the
  4M2P mixed-signal option but does not calibrate that option's BEOL or its
  fourth metal. This caveat is carried in `model_contract.yaml` and
  `model_maturity.yaml`.

### 2.14 PEX maturity ladder

| level | what it is | status |
|---|---|---|
| PEX v0 `mosis_wat_rc` | analytical RC from measured WAT coefficients | **implemented** (`historical_measured`) |
| PEX v1 `field_solver_estimated` | reconstructed BEOL stack + external field solver | **implemented as contract** (`field_solver_estimated`, `calibrated: false`) |
| foundry QRC / signoff | licensed RC table | **unavailable** |

Both v0 and v1 are research flows. Neither is a foundry QRC replacement, and the
manifest says so in `flow.signoff: false` and in each profile's `output.signoff`.

**v1 is input-only — no field solver is executed.** No field solver
(FastCap / FasterCap / Palace) is installed in this environment, so the port
deliberately stops at the solver's *input*: the parameterised BEOL fit plus the
7-pattern canonical sweep manifest. `scripts/gen_field_solver_sweep.py` emits
that manifest and the contract validates it, but nothing in this repository
invokes a solver, and no solved RC table is claimed anywhere. This is recorded
machine-readably in the manifest:

```yaml
flow:
  solver_availability:
    status: not_installed_locally
profiles:
  field_solver_estimated:
    solver_execution: not_performed
    solver_availability: not_installed_locally
```

So `field_solver_estimated` means "the reconstruction is parameterised and the
solver input is ready", **not** "a field solve has been run". Running the solver
later is the single step that would turn v1 from a contract into data — and it
must be re-validated against the acceptance band before any number is quoted.

---

## 3. What was implemented

| artifact | purpose |
|---|---|
| `profiles/tsmc035_4m2p/layers.yaml` | 32 layers / 21 available, parsed from the CDK (`scripts/parse_cdk_layers.py`) |
| `profiles/tsmc035_4m2p/rules.yaml` | reference-oracle DRC/LVS selection (`scmos_reference`, `rule_family scmos_subm`, λ 0.2) |
| `profiles/tsmc035_4m2p/devices.yaml`, `devices/bindings.yaml`, `devices/symbol_netlist.yaml`, `symbols.yaml`, `xschem_smoke.yaml` | core MOS4 device/symbol/SPICE contract |
| `profiles/tsmc035_4m2p/reference/manifest.yaml` | shared SCMOS reference DRC/LVS decks |
| `profiles/tsmc035_4m2p/models/tsmc035_4m2p.lib` | N88Y BSIM3v3.1 cards (`tsmc35N`, `tsmc35P`) |
| `profiles/tsmc035_4m2p/model_contract.yaml`, `model_maturity.yaml` | model authority separation + maturity |
| `profiles/tsmc035_4m2p/gds_layer_map.yaml` | provenance-aware historical SCMOS stream map |
| `profiles/tsmc035_4m2p/sources.yaml` | process identity + full provenance chain |
| `profiles/tsmc035_4m2p/pex/manifest.yaml` | PEX v0 + v1 contract |
| `profiles/tsmc035_4m2p/pex/tsmc035_wat_reference.yaml` | 5 coefficient sets + recorded local and external cross-checks |
| `profiles/tsmc035_4m2p/pex/tsmc035_beol_public_fit.yaml` | parameterised BEOL reconstruction |
| `common/pex/wat_rc.py` | **PEX v0 engine** (analytical R/C, provenance-enforcing) |
| `scripts/run_wat_pex.py` | PEX v0 CLI |
| `scripts/run_wat_pex_smoke.py` | PEX v0 smoke over every `wat_analytical_rc` profile |
| `scripts/test_tsmc035_pex.py` | port verification (identity, map, v0 arithmetic + refusals, cross-check, v1, SPICE, capabilities) |
| `schema/profile_collateral_matrix.yaml` | new `wat_analytical_rc` route entry |
| `common/process_ir.py` | `pex_rc = "historical_measured_rc"` capability for the new extractor |
| `scripts/test_profile_collateral_matrix.py`, `scripts/test_field_solver_contracts.py` | contract coverage for the new route/profile |

### PEX v0 model

```
R_ohm = R_sheet · L/W + N_contact · R_contact + N_via · R_via
C_aF  = C_area · A_overlap + C_fringe · L_edge
```

This is deliberately wider than the repository's existing `r_only_python`
backend (which refuses contact/via resistance) and narrower than a field solver.
It never guesses: a missing coefficient raises, a via without an explicit target
raises, and a coefficient set without provenance is refused.

---

## 4. Verification performed

| check | command | result |
|---|---|---|
| port verification | `python3 scripts/test_tsmc035_pex.py` | **PASS** |
| collateral matrix | `python3 scripts/test_profile_collateral_matrix.py` | **PASS** (13 profiles) |
| field-solver contracts | `python3 scripts/test_field_solver_contracts.py` | **PASS** (6 profiles) |
| ProcessIR contracts | `python3 scripts/test_process_ir.py` | **PASS** (13 profiles) |
| PEX v0 CLI | `python3 scripts/run_wat_pex.py --profile tsmc035_4m2p …` | 6700 aF = 38·100 + 58·50; `signoff: false`; typo in a key fails loudly |
| reference DRC | `python3 scripts/run_drc.py --profile tsmc035_4m2p --deck reference …` | deck resolves and executes; rule codes 2.x–8.x + `saveDerived`; violation fixture yields strictly more markers (76 vs 32) |
| reference LVS extraction | `run_lvs.extract(profiles/tsmc035_4m2p, …)` | **1 `nmos4` + 1 `pmos4`**, netlist `m1 … tsmc35N w=2 l=0.6` / `tsmc35P`; header `TSMC_CMOS035_4M2P prefix=tsmc35` |
| PEX v0 smoke (all WAT profiles) | `python3 scripts/run_wat_pex_smoke.py` | **PASS** — 16 segments / 6 pairs, all R and C positive, `signoff: false` |
| field-solver **input** generation | `python3 scripts/gen_field_solver_sweep.py --profile tsmc035_4m2p` | 7 canonical patterns, `calibrated: false`, `signoff: false` — **input only, solver never run** |
| SCMOS family suites (KLayout on PATH) | `test_scmos_extension_lvs`, `test_recognition_ir`, `test_hvcmos_contracts`, `test_scmos_rule_families` | **PASS** |

The LVS extraction is the strongest end-to-end result: a layout drawn on the
audited layer map extracts to a netlist that binds directly to the shipped N88Y
model cards with the correct prefix.

**Two honesty notes on the test run:**

1. The reference DRC reports `offgrid` and rule `6.1` markers even on the "clean"
   fixture. The shared fixture generator
   (`common/tests/make_drc_testcase.py`) is authored for AMI C5N (λ = 0.3 µm,
   grid 0.15 µm), while D35 is λ = 0.2 µm / grid 0.1 µm. Those markers are a
   **fixture-grid artifact**, not a deck failure. A D35-specific fixture would be
   needed for a clean DRC baseline.
2. `scripts/test_stdcell_spice_pex.py` fails, but **pre-existing and unrelated**:
   `schema/stdcell_spice_pex_readiness.yaml` expects `ams_c35` to have
   `pex_runtime: false`, while the committed `ams_c35` manifest now enables a
   native runtime PEX. Verified by reverting this port's `common/process_ir.py`
   change and re-running: `ams_c35` still reported `pex_runtime=True`. That
   failure comes from the earlier ams_c35 native-PEX work, not from this port.

---

## 5. Residual unknowns and tapeout blockers

| # | blocker | why it matters | what would clear it |
|---|---|---|---|
| 1 | Current TSRI/foundry stream map unavailable | a GDS built on the historical SCMOS map may not stream out correctly on the current kit | licensed TSRI `TSMC035_2P4M` stream map; §6 verification hook in `d35_scmos_layer_map.md` |
| 2 | No foundry QRC / PEX table | extracted RC is a research estimate | licensed RC techfile or foundry-extracted tables |
| 3 | No HV (thick-oxide) model card | the 5 V device class is unusable | official TSMC 0.35 HV SPICE card |
| 4 | No corner pack (`ss`/`ff`/etc.) | signoff timing/leakage impossible | foundry corner models |
| 5 | Poly1/Poly2 film thickness + permittivity not published | limits field-solver accuracy | official film table / TEM cross-section |
| 6 | Substrate resistivity/epi thickness unknown | no distributed substrate network | official substrate spec |
| 7 | Historical WAT is 1998–2005 | not the 2026 revision | current-revision WAT from the foundry |
| 8 | LO_EPI/MM_EPI FEOL confound unresolved | coefficient-set selection for a silicided variant | original report text with silicide splits |
| 9 | No D35-specific DRC fixture | clean DRC baseline unproven | λ = 0.2 / grid 0.1 SCMOS fixture |
| 10 | No field solve performed (solver not installed) | PEX v1 is a validated input, not data | run FastCap/FasterCap/Palace on the emitted sweep manifest and check the ±15 % acceptance band |

---

## 6. Engineering notes worth carrying forward

* **`yamlish` has no block-scalar support.** A `>-` or `|` value does not raise —
  it silently truncates the document at that point. Nine such values were
  introduced and then removed during this port; `scripts/test_tsmc035_pex.py`
  now guards the profile against the pattern. This is a general hazard for
  hand-written profile fragments in this repository.
* **`scripts/run_drc.py` writes `scmos_markers.gds` into the repository root** as
  a side effect, overwriting a tracked file. It was restored with
  `git checkout -- scmos_markers.gds`. Worth knowing before running DRC in a
  dirty tree.
* **`scripts/gen_drc.py` / `gen_lvs.py` only accept `engine: scmos_authoritative`.**
  A profile on `engine: scmos_reference` (this one, and `tsmc025_deep`) is never
  regenerated, so `scripts/conformance.py` (which compares two decks) cannot be
  used for it — `run_drc.py --deck reference` is the applicable gate.

---

## 7. Open questions for the requester

1. **"DEEP"**: does the request's "D35 SUBM/DEEP" refer to the MOSIS DEEP ladder
   (in which case §2.4 applies — D35 has no DEEP option), or to a TSRI-internal
   naming for a deep-submicron rule set? A TSRI document would settle it.
2. **Silicide**: is the intended D35 variant silicided or non-silicided
   source/drain? This selects between the LO_EPI-class and MM_EPI-class FEOL
   coefficients (§2.12).
3. **Current revision**: is there a 2026 D35 WAT/parametric report? Everything
   here is anchored to 1998–2005 data.
4. **HV**: is the 5 V thick-oxide class actually in scope? If so, a model card is
   the gating item.

---

## 8. Policy compliance

| repository rule | how it is satisfied |
|---|---|
| unknown contact/via/junction/substrate values are never guessed | missing coefficients raise; substrate network declared unavailable; `excluded_terms` is explicit |
| public reference maps must declare source and `tapeout_eligible: false` | `gds_layer_map.yaml` does both |
| `datatype 0` must be presented as a serialisation convention | `gds_policy.datatype.authority: siliconcraft_convention` |
| historical data must not be presented as signoff | `calibrated_to_current_d35: false`, `signoff: false`, `external_unverified` on every external set |
| maturity labels | `process_maturity.level: L1`, `status: historical_foundry_family_reference` |

---

## 9. References

**Local first-hand (verified in this environment)**

* NCSU CDK 1.6.0 — `skill/globalData.il`, `techfile/tsmc_04_4m2p.tf`,
  `pipo/streamInLayermap`, `pipo/cifInLayermap`, `techfile/divaDRC.rul`,
  `techfile/divaLVS.rul`, `models/hspice/public/publicModel/tsmc35N`,
  `models/hspice/public/publicModel/tsmc35P`,
  `models/MOSIS_reports/n88y-params.txt` (tree: `../ncsu-cdk-1.6.0`).
* Repository: [`process_flow_audit.md`](process_flow_audit.md) (N88Y vs T27K
  silicide separation), [`historical_scmos.md`](historical_scmos.md),
  [`mosis_evidence/tsmc035_cross_section.md`](mosis_evidence/tsmc035_cross_section.md),
  [`mosis_evidence/t28m_lo_epi-params.txt`](mosis_evidence/t28m_lo_epi-params.txt)
  (precedent for archiving a MOSIS report verbatim).
* `schema/scmos_process_matrix.yaml`, `schema/pex_public_contract.yaml`,
  `schema/layer_map_provenance.yaml`, `common/process_ir.py`.

**Requester-supplied, NOT re-verified offline** (full list in
`profiles/tsmc035_4m2p/sources.yaml`)

* MOSIS TSMC SCN035 MM_EPI report, run T2AF —
  <https://etd.ohiolink.edu/acprod/odb_etd/ws/send_file/send?accession=ucin1078349985&disposition=attachment>
* MOSIS TSMC SCN035 MM_EPI report, run T59N —
  <https://etda.libraries.psu.edu/files/final_submissions/3071>
* MOSIS TSMC 0.35 LO_EPI report, run T19P —
  <https://etd.ohiolink.edu/acprod/odb_etd/ws/send_file/send?accession=ucin1059399964&disposition=inline>
* US20110008962A1 — <https://patents.google.com/patent/US20110008962A1/en>
* PMC11859862 — <https://pmc.ncbi.nlm.nih.gov/articles/PMC11859862/>
* OWTU thesis TC-OWTU-5171 —
  <https://www.collectionscanada.gc.ca/obj/thesescanada/vol2/OWTU/TC-OWTU-5171.pdf>
* MOSIS SCMOS 8.0 technology-code table (`SCN4ME` / `SCN4ME_SUBM`) — no stable
  URL captured.
* Early Taiwan MEMS/mixed-signal work naming "TSMC 0.35um Mixed-Signal 2P4M
  Polycide 3.3/5V (MEMS_35)" with Calibre XRC PEX — no stable URL captured.

**Quoted verbatim inside local files** (the live URLs were not fetched)

* MOSIS FAQ 4.0 `faq-design.html#4.0` (Thick_Active semantics) — quoted in
  `techfile/divaDRC.rul` lines 94–101.
* MOSIS news 1999-03-01 `990301-ami-c5.html` (poly2 capacitors, not
  transistors, for TSMC 0.35u) — quoted in `techfile/divaDRC.rul` lines 79–89.
