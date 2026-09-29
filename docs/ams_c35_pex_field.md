# ams C35: PEX and field-solver observation (status update)

Companion files: `profiles/ams_c35/c35b4c3_stack.yaml` (ENG-182 Rev.6 nominal
stack), `profiles/ams_c35/reference/rc_coefficients.yaml` (OpenRCX reference
coefficient table), `profiles/ams_c35/pex/manifest.yaml`,
`docs/ams_c35_rf.md`, `docs/ams_c35_lambda_conformance.md`.

## 1. Ordinary signoff PEX for C35 is RC + coupling-C, NOT RLCK

- NUS Analog IC Design Manual: `Extraction Mode: xRC`, `Transistor Level`,
  `R + C + CC`, **No Inductance**.
- Cambridge C35 lab manual: `C + CC`, output `nor2x.pex.c+cc.dspf`;
  layer-to-layer and layer-to-substrate capacitance.
- Rostock AMS HIT-Kit tutorial: `QRC` → `Assura Quantus-QRC`, `c35b4c3`,
  ruleset `Typical`; Coupled C (signal↔signal) vs Decoupled C
  (net↔power/ground).
- Europractice: QRC is the C35 parasitic extraction tool.

Reference hierarchy:

```
Foundry:   QRC calibrated technology  ->  golden RC
Open:      simple geometry formulas -> OpenRCX/Magic PEX
           -> 2D/3D field-solver calibration
```

Target: **R + C_ground + C_coupling → DSPF/SPEF/extracted SPICE**. Inductance
is out of scope for ordinary PEX; RF inductors are ENG-188 macros.

## 2. Data status after the ENG-182 Rev.6 direct mirror

### Resolved (first-hand, in the repo now)

| Quantity | Value | Where |
| --- | --- | --- |
| Dielectric εr (Note 24) | TFOX/TPROT1 3.9 · TILDFOX/TILDDIFF/TPOX 4.0 · TIMD1-3 4.1 · TPROT2 7.9 · Si 11.7 | c35b4c3_stack.yaml |
| Nominal thicknesses (thin-M4) | PROT2 1.000, PROT1 1.030, M4 0.925, M3 0.640, M2 0.640, M1 0.665, ILDFOX 0.645, POLY1 0.282, FOX 0.290 | c35b4c3_stack.yaml |
| Passivation composition | SiNx (PROT2) + SiOx (PROT1); **no polyimide for thin-M4** (polyimide = thick-top-metal only) | c35b4c3_stack.yaml |
| Metal sheet R spec | M1/M2/M3 0.07–0.12, M4 0.04–0.10 Ω/□ | rc_coefficients.yaml |
| VIA3 resistance | 1.2–3 Ω (0.5×0.5 µm²) | rc_coefficients.yaml |
| Vertical C (typical) | M1→WELL 0.029/0.044, M2→M1 0.036/0.048, M3→M2 0.036/0.048, M4→M3 0.036/0.053, M4→M2 0.014/0.039, M4→M1 0.008/0.033, M4→WELL 0.006/0.029 (fF/µm² / fF/µm) | rc_coefficients.yaml |
| Same-layer coupling (min w/s) | P1-P1 0.039, M1-M1 0.087, M2-M2 0.084, M3-M3 0.085, M4-M4 0.097 fF/µm | rc_coefficients.yaml |
| Fringe reduction rule | ΔC_fringe ≈ −0.8·C_coupling when an adjacent line is present | rc_coefficients.yaml |
| Area C methodology | C/A = ε0·εr/t (optical thickness); check: M2→M1 0.036 = ε0·4.1/1.0 µm ✓ | rc_coefficients.yaml |
| Perimeter/coupling methodology | SCAP FEM (Univ. Vienna), single edge / adjacent min-width lines | rc_coefficients.yaml |
| Electrical width correction | M2/M3 drawn 0.6 → effective 0.5 µm (−0.1 µm, from R structures) | rc_coefficients.yaml |
| Substrate | ρ = 14/19/24 Ω·cm non-epi → σ = 7.14/5.26/4.17 S/m | c35b4c3_stack.yaml |
| Junction depths | XJN = XJP = 0.2 µm, **XJNW = 3.5 µm** (Rev.3 "Corrected: XJNW"; drop the old Rev.2 2.0 µm) | c35b4c3_stack.yaml |
| n-well | R□ = 0.9/1.0/1.1 kΩ/□; equivalent slab d=3.5 µm, ρ_eq 0.35 Ω·cm, σ_eq 286 S/m (satisfies Rsh AND XJNW) | c35b4c3_stack.yaml |
| Sidewall angles (FIB/SEM) | min/avg/max per layer; nominal: M4 104°, M3 91°, M2 93°, M1 93°, VIA3 89°, VIA2 83°, VIA1 88°, CONT 88° | c35b4c3_stack.yaml |
| σ_eff backout | σ = 1/(Rsh·t): M1 1.88e7, M4 2.16e7 S/m | rc_coefficients.yaml |

### Still open (the honest remainder)

1. **Passivation actual thickness**: ENG-182 nominal 2.03 µm (PROT1+PROT2) vs
   ~1.6 µm reported on a real thin-M4 die → keep ENG-182 for PDK-nominal RC,
   allow re-calibration when fitting a real die.
2. **Corner rounding radius**: no quantitative AMS C35 value found → sharp
   trapezoid default; add `r_corner` only for high-frequency S-param /
   C-couple calibration.
3. **Vertical doping shape N_A(z) / N_D_well(z)**: not public (ENG-182 Note 4:
   SIMS/SRS extracted, only the final junction depth published). MOS NSUB is a
   compact-model body parameter (Note 12), NOT a wafer profile. Use ρ + σ +
   the n-well equivalent slab instead of inventing an implant shape.
4. **Sidewall details** (taper distribution, etch bias vs SEM): SEM stats
   exist; treat as statistics, keep the exact per-device profile as a
   calibration knob.

## 3. Validation loop (three test geometries, then the spiral)

Fixed first: `t_i`, `εr_i`, `R□_i`, `W_eff` — all ENG-182.

1. **Large plate** — `C_area(solver) ≈ C_area(ENG182)`: verifies εr/t.
2. **Isolated min-width wire** — `C_fringe/L ≈ C_perimeter(ENG182)`:
   introduces the sidewall trapezoid.
3. **Min-width / min-space pair** — `C12/L ≈ C_coupling(ENG182)`, then check
   the ΔC_fringe ≈ −0.8·C_coupling relation.
4. **ENG-188 spirals** — `Z(f), Q(f), SRF, Rsub, Csub` to fit substrate and
   high-frequency corrections (SP020S180D / SP026S200D fitted values in
   c35b4c3_stack.yaml calibration targets).

Solver angle convention: the FIB/SEM angles are as defined in the source
paper — do not feed e.g. 104° directly into a solver that expects the
deviation-from-vertical angle; convert first.

## 4. Conclusion

Ordinary RCX for C35B4C3 can now be rebuilt by the original methodology:
the R/C/ε values are recovered and the remaining uncertainty is confined to
process 3D micro-geometry (passivation thickness, sidewall profile, corner
rounding) and the implant profile — not R/C/ε themselves.
