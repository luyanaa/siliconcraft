# ams C35 RF models (ENG-188 Rev 5.0) and the SCMOS_RF patch architecture

This file records the historical ENG-188 Rev 5.0 RF model contract used by the
repository; it is not a current licensed PDK specification. The ENG-188 PDF
mirror was inaccessible during this research pass. An accessible university
tutorial independently confirms the RF MOS model names and key limits; details
not covered there remain historical, unverified contract data.

## 1. RF MOS = BSIM3 core + extrinsic network (not a different BSIM)

`modnrf`/`modprf` keep the BSIM3v3.1 intrinsic transistor; ams replaces the
internal D/B and S/B junction diodes with EXTERNAL diodes so the substrate
network can be modeled, and wraps the core with:

```
G ---/\/\/\/--- Gint            RG gate resistance
D --/\/\/\/----                 RD drain resistance
S ----/\/\/\/--                 RS source resistance
              |                 RSUB1/RSUB2 substrate resistance (RSUB1=RSUB2)
            RSUB1/RSUB2         Djdb/Djsb external drain-bulk / source-bulk
              |                 junction diodes
          substrate             Mcore = BSIM3v3.1 intrinsic MOS
```

PMOS mirrors the structure with opposite diode orientation. A multi-finger
device is one equivalent MOS; the extrinsic network scales with finger count.

## 2. Validity envelope (restricted, not arbitrary-W/L scalable)

| Parameter | Limit (ENG-188 §2.1) |
| --- | --- |
| frequency | ≤ 6 GHz |
| L | fixed 0.35 µm |
| single-finger width wf | 5 or 10 µm |
| total W | NMOS ≤ 200 µm, PMOS ≤ 150 µm |
| gate contact | finger contacted on ONE side |
| W definition | W = ng × wf |
| example | W=90 µm, wf=5 µm, L=0.35 µm, ng=18, Ad=2.5 µm², As=2.69 µm², Pd=1.0 µm, Ps=1.63 µm |

## 3. Measured RF performance (Table 2.1, VDS = ±3 V)

| wf | NMOS fT | PMOS fT | NMOS fmax | PMOS fmax |
| --- | ---: | ---: | ---: | ---: |
| 5 µm | 28 GHz | 15 GHz | 49.9 GHz | 34.6 GHz |
| 10 µm | 28 GHz | 15 GHz | 36.6 GHz | 27.9 GHz |

fT is finger-width independent; fmax degrades with wider fingers — gate
resistance / distributed parasitics dominate. RF device contracts must
therefore carry finger width, finger count and gate-contact topology.

## 4. Where plain models stop (the ~1 GHz boundary)

- ENG-182 plain analog/mixed-signal MOS models are guaranteed to ≈1 GHz;
- ENG-188 RF models extend to 6 GHz (Rg + Rs/Rd + substrate R + external
  junction diodes + restricted RF layout).

This answers the "when does the SCMOS/compact abstraction break" question
for C35: not at 1 GHz (process limit), but as a MODELING boundary — above
~1 GHz you need the layout-dependent extrinsic wrapper.

## 5. Varactor (cvar)

Accumulation-mode MOS varactor: PMOS BSIM3v3.2 gate-bulk capacitance (Cgb)
as the core + RG + Ro1/2 (suppress inversion C rise) + Rw1/2 (well R) +
Dw1/2 (well/substrate junction). Envelope: few kHz–6 GHz; total W
100–1000 µm; wseg=6.6 µm fixed; L=0.65 µm fixed; row×col array (col/row 1–5).
Measured Cmax/Cmin ≈ 3.65–3.68 (~57 % tuning); min Q 41–80 at 2.4 GHz.
Reference: Molnar et al., IEEE TED 49(7), 2002.

## 6. RF passives (characterized macros, not arbitrary PEX)

| Primitive | Model | Notes |
| --- | --- | --- |
| spiral inductor | Ls+Rs+Cp+Cox1/2+Csub1/2+Rsub1/2 | fixed 3M/4M/thick libraries |
| differential inductor | Brune transformer (Ldc, LBp, LBs, k12, Rdc, RB, Re, CW, CB, COX/C, RSUB/C) | thick-metal only, 1.5–6 nH |
| CPOLYRF | Cpoly+Rs+Cpw+Rpw | ≤6 GHz, 0.1–5 pF; Q 437→13.5 (0.12→4 pF @2.4 GHz) |
| CMIMRF | Cmim+Rs+Cmw | Rs≈0.1 Ω (VIA2-contact-limited); connecting metal ≥2 µm wide |
| RPOLY2RF/RPOLYHRF | Rpoly+Cp+Cpw | W 1–3 µm; L ≤90/30 µm; n-well terminal to substrate/AC gnd |

Key PDK lesson: via/contact parasitic enters the device model contract
(MIM Rs is computed from VIA2 contact resistance), not only far-end PEX.

## 7. Model names / revisions (ENG-188 Rev 5.0)

modnrf 3.0 · modprf 3.0 · cvar 3.0 · stxxxayyyb (spiral) 3.0 · dixxpt
(differential) 1.0 · cpolyrf 4.0 · cmimrf 1.0 · rpoly2rf 4.0 · rpolyhrf 1.0.

## 8. SCMOS_RF patch architecture (take-away for siliconcraft)

```
SCMOS/BSIM compact model
  ├── ordinary MOS              < ~1 GHz (λ rules define geometry)
  └── RF MOS primitive          ~1-6 GHz
        ├── fixed/minimum L, constrained finger W
        ├── Rg + Rd/Rs + substrate network + external junction C
        └── geometry-aware scaling (W = ng*wf)
RF passives
  ├── R → R + Csubstrate      C → C + ESR + substrate
  ├── varactor → BSIM Cgb + Rwell/Rg
  └── L → characterized RLC/Brune macro
```

λ rules keep doing geometry manufacturability; the RF patch defines a finite
set of RF-qualified layout topologies plus extrinsic models. AMS C35 is the
reference precedent for this split — do not try to turn SCMOS λ rules into
"RF rules".

The C35 profile has module-scoped RF MOS, RF passive, and inductor contracts.
They remain `contract_only`: no local C35 RF PCell, executable LVS device
recognizer, simulator wrapper, licensed model card, or device-level EM result
is claimed. O1 is deferred; the historical runset's HRES switch conflicts with
the current Europractice 2026 O1 listing, so no O1 resistor capability is
inferred. CMIM/CMIMRF are disabled in the active C3 target because METCAP is
off.

The historical public Calibre runset provides terminal declarations for
`nmosrf`/`pmosrf` (G,S,D,B), `rpoly2rf`/`rpolyhrf` (POS,NEG,SUB),
`cpolyrf` (POS,NEG,SUB), and fixed spiral variants (POS,NEG,SUB). It does not
provide a `dixxpt` extraction declaration; the differential inductor remains
an ENG-188 model contract without repository LVS recognition.

The PEX manifest lists Palace only as a candidate field solver. The repository
contains no `gds2palace` bridge, and the generic BEOL solver path cannot
transform an RF device into a characterized ENG-188 macro. No Palace RF result
is claimed.

## 10. Sources and model-card access

- AMS [2016 iPDK announcement](https://ams-osram.com/news/press-releases/ams-releases-interoperable-pdk-for-its-0-35mm-analog-specialty-processes)
  says the licensed environment includes characterized simulation models,
  Calibre/Assura extraction and verification runsets, and PyCells.
- CMC [AMS 0.35 µm kit access](https://www.cmc.ca/ams-0-35-%C2%B5m-design-kits/)
  requires a site license and confidentiality agreements for C35B4C3/C35B4O1;
  it also requires the current kit for fabrication DRC signoff.
- The accessible [RF LNA tutorial](https://www.emse.fr/~dutertre/documents/TP_RF_LNA_MOS.pdf)
  names `modnrf`/`modprf`, confirms their 6 GHz limit, fixed 0.35 µm gate
  length, 5/10 µm finger widths, total-width limits, and the `poly2rf` model.
- The [historical AMS Calibre runset](https://raw.githubusercontent.com/jjwikner/daisy/c6d8341f36d734a55b9ac0902547744c93cd4cd6/daisy/pdk/ams035/pv/calibre/cac35b4rules_all.run)
  provides the extraction pin metadata above, but is not the current licensed
  signoff deck.

No C35 RF model-card files were recovered from public sources or this
repository. Keep RF `model_library` entries null until the licensed kit and
current model wrappers are available.
