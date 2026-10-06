# D35 physical BEOL/FEOL stack — evidence and reconstruction

Evidence file for the TSMC 0.35 µm Mixed-Signal 2P4M Polycide 3.3/5 V process
(TSRI "D35", NCSU CDK `TSMC_CMOS035_4M2P`).

Consumed by `profiles/tsmc035_4m2p/pex/tsmc035_beol_public_fit.yaml` (the PEX v1
field-solver reconstruction).

---

## 1. Official cross-section (4-metal option)

Source: "TSMC035um Thickness Rule" — official TSMC 0.35 µm design rules,
third-party-hosted mirror (scribd presentation 363796096); archived in this
repository as [`tsmc035_cross_section.md`](tsmc035_cross_section.md).

| Layer | Thickness (µm) | Evidence class |
|---|---|---|
| M4 | 0.925 | official document value |
| Via3 / Oxide4 (M3→M4 ILD) | 1.1 | official document value |
| M3 | 0.64 | official document value |
| Via2 / Oxide3 (M2→M3 ILD) | 1.1 | official document value |
| M2 | 0.64 | official document value |
| Via1 / Oxide2 (M1→M2 ILD) | 1.1 | official document value |
| M1 | 0.67 | official document value |
| Thick oxide (poly→M1) | 1.09 | official document value |
| Gate oxide | 0.0078 (78 Å) | official document value |
| Poly1 / Poly2 film | not stated | **gap** |
| Substrate resistivity | not stated | **gap** |
| Relative permittivity | not stated | **gap** |

Total stack height **7.275 µm**.

### Independent corroboration of the M4 tier

The measured sheet resistances corroborate the geometry: N88Y (3-metal)
MTL3 = 0.04 Ω/□ equals T2AF/T59N (4-metal) MTL4 = 0.04 Ω/□, and N88Y
MTL1/MTL2 = 0.07 Ω/□ equals T2AF/T59N MTL1/MTL2/MTL3 = 0.07 Ω/□. The thick top
tier is M4 at 0.925 µm. See
[`d35_wat_pex_data.md`](d35_wat_pex_data.md) §4.

---

## 2. Requester-supplied thickness priors (not re-verified offline)

| source | claim | class | note |
|---|---|---|---|
| US20110008962A1 (patent) | M1 ≈ 0.665, M2 ≈ 0.645, M3 ≈ 0.645, M4 = 0.925 µm; IMD ≈ 1.0 µm; field oxide ≈ 0.297 µm | patent embodiment example | an embodiment example is not a guaranteed process value; the source also contains an apparent M3/M4 inconsistency |
| PMC11859862 (paper) | Poly1 ≈ 0.278 µm, Poly2 ≈ 0.180 µm; M1–M4 are Al with a via/IMD stack | peer-reviewed paper | supplies the poly film thicknesses the official deck omits |
| OWTU thesis TC-OWTU-5171 | M2 ≈ 0.6 µm; oxide stack of order 1 µm | thesis | consistent with the official deck |
| AMS C35 ENG-182 Rev.6 (different foundry, same 0.35 µm generation) | M1 0.665 µm, IMD1 1.0 µm | different-foundry collateral | numerically consistent with the TSMC cross-section; no licensing relationship asserted |
| requester description: early Taiwan MEMS/mixed-signal work naming "TSMC 0.35um Mixed-Signal 2P4M Polycide 3.3/5V (MEMS_35)" using Calibre XRC | process identity + that PEX was historically done with a commercial field solver | secondary literature | supports the identity claim and the PEX-v1 approach |

URLs for these are recorded in
[`profiles/tsmc035_4m2p/sources.yaml`](../../profiles/tsmc035_4m2p/sources.yaml)
under `requester_supplied_external.references`. **They were not fetched in this
port** (no network egress), so they are `not_reverified_offline`.

---

## 3. Reconstruction used by PEX v1

`tsmc035_beol_public_fit.yaml` declares:

```yaml
fit_parameters:
  metal_thickness_um:  {metal1: 0.67, metal2: 0.64, metal3: 0.64, metal4: 0.925}  # official
  ild_thickness_um:    {metal1_metal2: 1.1, metal2_metal3: 1.1, metal3_metal4: 1.1}  # official
  ild_relative_permittivity: fitted (SiO2 3.9 assumed until fitted)
```

* conductor and ILD thicknesses are **official document values**;
* the permittivity is a **fitted parameter** — the deck states none, and assuming
  SiO₂ 3.9 is recorded as an assumption, not a measurement;
* substrate effective permittivity is a research placeholder only;
* `fit_target` is the local first-hand **T02F (4M/2P)** coupling matrix from the
  NCSU CDK techfile, cross-checked against the local N88Y matrix, with a 15 %
  acceptance band.

The fit is a **plausibility reconstruction**, not a calibration:
`calibrated: false`, `signoff.foundry_qrc: false`,
`signoff.tapeout_qualification: false`.

---

## 4. What would upgrade this

| unknown | needed |
|---|---|
| poly1 / poly2 film thickness | official film-thickness table or TEM/SEM cross-section for the shipped revision |
| relative permittivity per ILD tier | official electrical spec or measured C–V on a known area |
| substrate resistivity / epi thickness | official substrate spec; required for any distributed substrate network |
| M5/M6 (unused here) | only if a different option is targeted |
| current-revision stack drift | TSRI D35 process spec for the 2026 revision |

Until then PEX v1 stays `field_solver_estimated`.

---

## 5. References

* [`tsmc035_cross_section.md`](tsmc035_cross_section.md) — official TSMC 0.35 µm
  4-metal thickness rules (archived extraction; third-party mirror of official
  content).
* `../ncsu-cdk-1.6.0/models/MOSIS_reports/n88y-params.txt` — local first-hand
  sheet/contact/via resistance and capacitance.
* `../ncsu-cdk-1.6.0/techfile/tsmc_04_4m2p.tf` — lambda 0.2, grid 0.1, metal
  availability.
* US20110008962A1 — <https://patents.google.com/patent/US20110008962A1/en>
  (requester-supplied; **not re-verified offline**).
* PMC11859862 — <https://pmc.ncbi.nlm.nih.gov/articles/PMC11859862/>
  (requester-supplied; **not re-verified offline**).
* OWTU thesis TC-OWTU-5171 —
  <https://www.collectionscanada.gc.ca/obj/thesescanada/vol2/OWTU/TC-OWTU-5171.pdf>
  (requester-supplied; **not re-verified offline**).
