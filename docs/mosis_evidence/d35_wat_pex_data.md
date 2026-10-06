# D35 WAT / PEX reference data

Evidence file for the TSMC 0.35 µm Mixed-Signal 2P4M Polycide 3.3/5 V process
(TSRI "D35", NCSU CDK `TSMC_CMOS035_4M2P`, MOSIS code `SCN4ME_SUBM`).

Consumed by `profiles/tsmc035_4m2p/pex/tsmc035_wat_reference.yaml` and the
`mosis_wat_rc` analytical PEX flow (`common/pex/wat_rc.py`).

---

## 0. Verification-environment gap (read this first)

The requester supplied several external URLs (university theses reproducing
official MOSIS reports, a patent, a journal paper). **This port was produced in
a sandbox with no working network egress**, so those documents could not be
re-fetched or independently re-read:

* `web_search` → `DeepSeek API error (HTTP 402): Insufficient balance`
* `web_fetch` on a PMC article → `URL hostname resolves to a non-public IP address`

Consequently the external numbers are recorded as
`verification_status: not_reverified_offline` and are **never** promoted to
signoff authority. To keep the data honest rather than merely quoted, every
external quantity that has a counterpart in the **local, first-hand** MOSIS
report is cross-checked against it (§4). That cross-check is the actual evidence
produced by this port; the external numbers themselves remain reported, not
verified.

---

## 1. Local first-hand anchor — MOSIS run N88Y

Source: `../ncsu-cdk-1.6.0/models/MOSIS_reports/n88y-params.txt`
(official MOSIS parametric report bundled in the NCSU CDK mirror).
Evidence class: **local_first_hand_source_file** — verified by reading the file.

Header (verbatim):

```
                          MOSIS PARAMETRIC TEST RESULTS

          RUN: N88Y                                         VENDOR: TSMC
   TECHNOLOGY: SCN035H                               FEATURE SIZE: 0.35 microns
...
COMMENTS: SMSCN3ME04
...
COMMENTS: DL_TSMC_035
```

Note `SMSCN3ME04`: the report itself is tagged to the **SCN3ME** (3-metal,
mixed-signal, epi) option family. This is independent support for the lineage
claim that the D35 4M2P mixed-signal option descends from the same MOSIS SCMOS
mixed-signal epi line (SCN3ME → SCN4ME).

Process parameters (lines 44–52, verbatim):

```
PROCESS PARAMETERS    N+ACTV  P+ACTV  POLY  POLY2  MTL1   MTL2   MTL3  UNITS
 Sheet Resistance      79.1   153.4   7.4   47.4   0.07   0.07   0.04  ohms/sq
 Contact Resistance    54.8   118.5   5.6   31.4          1.31   1.42  ohms
 Gate Oxide Thickness  76                                              angstrom
PROCESS PARAMETERS       N_WELL   N\PLY     UNITS
 Sheet Resistance        1011      1081     ohms/sq
COMMENTS: N\POLY is N-well under polysilicon.
```

Capacitance parameters (lines 59–72, verbatim):

```
CAPACITANCE PARAMETERS N+ACTV  P+ACTV  POLY  POLY2 MTL1 MTL2 MTL3 N_WELL UNITS
 Area (substrate)      921    1408     117          23   11    6    55   aF/um^2
 Area (N+active)                      4562  1035    28   16   11         aF/um^2
 Area (P+active)                      4561   635                         aF/um^2
 Area (poly)                                 894    46   15    9         aF/um^2
 Area (poly2)                                       44                   aF/um^2
 Area (metal1)                                           36   13         aF/um^2
 Area (metal2)                                                36         aF/um^2
 Fringe (substrate)    299     385                  54   30   31         aF/um
 Fringe (poly)                                      61   37   28         aF/um
 Fringe (metal1)                                         56   35         aF/um
 Fringe (metal2)                                              53         aF/um
 Overlap (N+active)                    306                               aF/um
 Overlap (P+active)                    590                               aF/um
```

Read out as conductor-pair coefficients (the form the PEX flow uses):

| pair | area (aF/µm²) | fringe (aF/µm) |
|---|---|---|
| metal1–metal2 | 36 | 56 |
| metal1–metal3 | 13 | 35 |
| metal2–metal3 | 36 | 53 |
| poly–metal1 | 46 | 61 |
| poly–metal2 | 15 | 37 |
| poly–metal3 | 9 | 28 |
| poly2–metal1 | 44 | — (not reported) |
| metal1–substrate | 23 | 54 |
| metal2–substrate | 11 | 30 |
| metal3–substrate | 6 | 31 |
| poly–substrate | 117 | — (not reported) |
| nactive–substrate | 921 | 299 |
| pactive–substrate | 1408 | 385 |
| nwell–substrate | 55 | — |
| poly over nactive (gate) | 4562 | overlap 306 |
| poly over pactive (gate) | 4561 | overlap 590 |

Device / benchmark data (lines 14–42, 74–85):

| quantity | N-channel | P-channel |
|---|---|---|
| Vth, min 0.60/0.4 (V) | 0.54 | −0.77 |
| Vth, short 3.6/0.4 (V) | 0.58 | −0.76 |
| Vth, large 3.6/3.6 (V) | 0.55 | −0.76 |
| Idss (µA/µm) | 485 | −218 |
| Vpt (V) | 9.6 | −8.9 |
| Gamma (V^0.5) | 0.62 | 0.39 |
| Delta length drawn−electrical (µm) | −0.05 | −0.10 |
| Delta width drawn−electrical (µm) | 0.15 | 0.10 |
| K' (µA/V²) | 94.4 | −33.3 |

```
 Ring Oscillator Freq.   DIV4 (31-stage,3.3V)   196.17  MHz
 Ring Oscillator Power   DIV4 (31-stage,3.3V)     5.83  uW/MHz/g
```

Gate oxide 76 Å = 7.6e-9 m, which matches the shipped CDK card
(`models/hspice/public/publicModel/tsmc35N`, `TOX = 7.6E-9`) — confirming the
shipped `tsmc35N`/`tsmc35P` cards are the N88Y run.

**Limitation:** N88Y is a **3-metal** run (MTL1..MTL3 only). It supplies no M4
and no Via3, so it cannot by itself define the 4-metal option's top tier.

---

## 2. Requester-supplied external sets

All rows below are `external_reported` / `not_reverified_offline`.

| set | run | option | metals | URL | nature |
|---|---|---|---|---|---|
| `t2af_mm_epi_4m` | T2AF | MM_EPI | 4 | [OhioLINK ucin1078349985](https://etd.ohiolink.edu/acprod/odb_etd/ws/send_file/send?accession=ucin1078349985&disposition=attachment) | university thesis reproducing an official MOSIS report |
| `t59n_mm_epi_4m` | T59N | MM_EPI | 4 | [Penn State ETDA 3071](https://etda.libraries.psu.edu/files/final_submissions/3071) | university thesis reproducing an official MOSIS report |
| `t19p_lo_epi_4m` | T19P | LO_EPI | 4 | [OhioLINK ucin1059399964](https://etd.ohiolink.edu/acprod/odb_etd/ws/send_file/send?accession=ucin1059399964&disposition=inline) | university thesis reproducing an official MOSIS report |

### T2AF (MM_EPI, 4M) — sheet and cut resistance

| quantity | N+ | P+ | poly | poly2 | M1 | M2 | M3 | M4 | N-well |
|---|---|---|---|---|---|---|---|---|---|
| Rsheet (Ω/□) | 79.4 | 154.0 | 8.7 | 47.1 | 0.07 | 0.07 | 0.07 | 0.04 | ~1000 |
| contact R (Ω) | 62.7 | 132.7 | 7.2 | 34.1 | — | — | — | — | — |
| via R (Ω) | — | — | — | — | via1 1.24 | via2 0.99 | via3 0.88 | — | — |

### T2AF coupling capacitance

| pair | area (aF/µm²) | fringe (aF/µm) |
|---|---|---|
| metal1–metal2 | 38 | 58 |
| metal1–metal3 | 14 | 37 |
| metal1–metal4 | 9 | 29 |
| metal2–metal3 | 39 | 53 |
| metal2–metal4 | 14 | 38 |
| metal3–metal4 | 39 | 65 |

### T59N (MM_EPI, 4M) — partial

M1/M2/M3 = 0.07 Ω/□, M4 = 0.04 Ω/□, N-well ≈ 998 Ω/□.

### T19P (LO_EPI, 4M)

| quantity | value |
|---|---|
| N+ Rsheet | ≈3.6 Ω/□ |
| P+ Rsheet | ≈2.7 Ω/□ |
| coupling area (M1–M2 / M1–M3 / M1–M4 / M2–M3 / M2–M4 / M3–M4) | 39 / 14 / 9 / 35 / 14 / 36 |
| coupling fringe (same order) | 53 / 37 / 27 / 52 / 35 / 59 |

---

## 3. Why T2AF is the 4-metal D35 reference

The D35 marketing name is "TSMC 0.35 µm **Mixed-Signal** 2P4M Polycide
3.3/5 V": mixed-signal **and** 4-metal. Among the available sets:

* N88Y — local, verified, but **3-metal** and tagged SCN3ME;
* T2AF / T59N — **MM_EPI**, **4-metal** → closest option match;
* T19P — **LO_EPI**, 4-metal, but a different FEOL class (§5).

`d35_reference_set: t2af_mm_epi_4m` is therefore the default, with N88Y retained
as the verified cross-check anchor. `capability_separation.rule` in the data file
forbids blending LO_EPI and MM_EPI coefficients.

---

## 4. Cross-check: local N88Y vs external T2AF

Computed by `common/pex/wat_rc.compare_sets` / `compare_coupling` and asserted in
`scripts/test_tsmc035_pex.py`, so the recorded deltas cannot go stale.

### Sheet resistance

| layer | N88Y (local, verified) | T2AF (external) | Δ |
|---|---|---|---|
| N+ active | 79.1 | 79.4 | **+0.4 %** |
| P+ active | 153.4 | 154.0 | **+0.4 %** |
| poly | 7.4 | 8.7 | +17.6 % |
| poly2 | 47.4 | 47.1 | −0.6 % |
| metal1 | 0.07 | 0.07 | 0.0 % |
| metal2 | 0.07 | 0.07 | 0.0 % |
| N-well | 1011 | ~1000 | −1.1 % |

### Contact / via resistance

| target | N88Y | T2AF | Δ |
|---|---|---|---|
| N+ contact | 54.8 | 62.7 | +14.4 % |
| P+ contact | 118.5 | 132.7 | +12.0 % |
| poly contact | 5.6 | 7.2 | +28.6 % |
| poly2 contact | 31.4 | 34.1 | +8.6 % |
| via1 | 1.31 | 1.24 | −5.3 % |
| via2 | 1.42 | 0.99 | −30.3 % |

### Coupling capacitance

| pair | N88Y area/fringe | T2AF area/fringe | Δ area | Δ fringe |
|---|---|---|---|---|
| metal1–metal2 | 36 / 56 | 38 / 58 | +5.6 % | +3.6 % |
| metal1–metal3 | 13 / 35 | 14 / 37 | +7.7 % | +5.7 % |
| metal2–metal3 | 36 / 53 | 39 / 53 | +8.3 % | 0.0 % |

### Top-metal tier mapping (structural corroboration)

N88Y (3-metal) **MTL3 = 0.04 Ω/□** equals T2AF/T59N (4-metal) **MTL4 = 0.04 Ω/□**,
while N88Y **MTL1/MTL2 = 0.07 Ω/□** equals T2AF/T59N **MTL1/MTL2/MTL3 = 0.07 Ω/□**.
The 3-metal run's top metal therefore sits in the same thickness class as the
4-metal option's M4 — independently corroborating the official cross-section
(§6, M4 = 0.925 µm being the thick tier).

### Assessment

* CBEOL (M1/M2 sheet resistance, M1–M2 / M1–M3 / M2–M3 coupling capacitance)
  agrees within ~10 %.
* FEOL N+/P+ active agrees to ~0.4 %.
* Real lot-to-lot spread exists on poly (17.6 %) and contact resistance
  (12–29 %).

This is why a historical WAT set is usable as a **research reference** but not as
a **signoff parameter set**.

---

## 5. Open question: the LO_EPI/MM_EPI FEOL gap is probably a silicide confound

T19P (LO_EPI) N+ ≈ 3.6 Ω/□ and P+ ≈ 2.7 Ω/□ versus MM_EPI/N88Y ≈ 79/154 Ω/□.
That is a factor of ~22 on N+ — far larger than any metal/CBEOL spread and much
larger than a plausible epi-resistivity effect on **source/drain sheet
resistance**, which is dominated by the junction/silicide stack, not by the
substrate epi.

A silicided source/drain is the natural explanation (silicided N+ S/D is
typically single-digit Ω/□; non-silicided is tens of Ω/□). The repository's own
process audit (`docs/process_flow_audit.md`) already separates the **non-silicided
N88Y** run from the **silicided T27K** run (N+ 3.3 Ω/□) on exactly this basis.

**Conclusion:** the LO_EPI vs MM_EPI difference as reported is confounded with
silicide/no-silicide. This is recorded as an **open question**, not resolved, and
is one reason the two sets are never blended. Resolving it requires the original
report text (wafer-level S/D implant/silicide splits), which could not be
fetched offline.

---

## 6. PEX v0 — `mosis_wat_rc` analytical model

Implemented in `common/pex/wat_rc.py`, CLI `scripts/run_wat_pex.py`,
contract `profiles/tsmc035_4m2p/pex/manifest.yaml`.

```
R_ohm = R_sheet[Ω/□] · L[µm] / W[µm]
      + N_contact · R_contact[Ω]
      + N_via     · R_via[Ω]

C_aF  = C_area[aF/µm²] · A_overlap[µm²]
      + C_fringe[aF/µm] · L_edge[µm]
```

Worked example (T2AF set, verified by `scripts/test_tsmc035_pex.py`):

| element | inputs | result |
|---|---|---|
| metal1 wire | 0.07 Ω/□, L=100 µm, W=0.6 µm | 11.6667 Ω |
| metal2 wire + 1 via1 | 0.07 Ω/□, L=50 µm, W=0.6 µm, via 1.24 Ω | 5.8333 + 1.24 = 7.0733 Ω |
| nactive + 2 contacts | 79.4 Ω/□, L=10 µm, W=0.6 µm, 62.7 Ω/cut | 1323.333 + 125.4 = 1448.733 Ω |
| metal1–metal2 coupling | A=100 µm², edge=50 µm | 3800 + 2900 = 6700 aF |

Honesty properties enforced by the engine and the test:

* a coefficient set without `provenance.authority` is refused;
* a missing coefficient (e.g. M4 on the 3-metal N88Y set, `via3` on N88Y,
  M2–M4 coupling on N88Y, any contact on metal1) raises instead of defaulting;
* a via count without an explicit `via_target` raises;
* every report carries `calibrated_to_current_d35: false`, `signoff: false`, and
  a `coefficient_set_verification` of `verified_local_report` or
  `external_unverified`.

Excluded terms are declared rather than silently omitted: junction capacitance
(owned by the compact model), substrate network (unavailable), lateral sidewall
coupling (outside the overlap/edge model), temperature correction (no
coefficients materialized).

---

## 7. PEX v1 — reconstructed BEOL field-solver flow

`profiles/tsmc035_4m2p/pex/tsmc035_beol_public_fit.yaml`, consumed by
`common/pex/field_solver.py::canonical_sweep_manifest`, maturity
`field_solver_estimated`, `calibrated: false`, `signoff: false`.

The fit target is the **measured** T2AF coupling matrix (§2) with the local N88Y
matrix as cross-check, acceptance band 15 %. Inputs are the official 4-metal
cross-section thicknesses (§6 of `d35_physical_stack.md`) plus a fitted relative
permittivity (SiO₂ 3.9 assumed until fitted). An external FastCap / FasterCap /
Palace run consumes the canonical sweep manifest and returns a research RC table.

---

## 8. References

* MOSIS parametric report **run N88Y**, technology **SCN035H**, vendor TSMC —
  `../ncsu-cdk-1.6.0/models/MOSIS_reports/n88y-params.txt` (local first-hand).
* NCSU CDK 1.6.0 shipped cards `models/hspice/public/publicModel/tsmc35N`,
  `tsmc35P` (local first-hand; header `* run N88Y`).
* MOSIS TSMC SCN035 **MM_EPI** report (run T2AF) —
  <https://etd.ohiolink.edu/acprod/odb_etd/ws/send_file/send?accession=ucin1078349985&disposition=attachment>
  (requester-supplied; **not re-verified offline**).
* MOSIS TSMC SCN035 **MM_EPI** report (run T59N) —
  <https://etda.libraries.psu.edu/files/final_submissions/3071>
  (requester-supplied; **not re-verified offline**).
* MOSIS TSMC 0.35 **LO_EPI** report (run T19P) —
  <https://etd.ohiolink.edu/acprod/odb_etd/ws/send_file/send?accession=ucin1059399964&disposition=inline>
  (requester-supplied; **not re-verified offline**).
* Repository process audit — [`docs/process_flow_audit.md`](../process_flow_audit.md)
  (N88Y vs T27K silicide separation).
