# ams C35: SCMOS_SUBM λ=0.2 abstraction vs full ENG-183

The ams_c35 profile uses the MOSIS SCMOS_SUBM abstraction (λ=0.20 µm,
SCN4ME_SUBM, matching the TSMC-licensed 0.35 µm 2P4M base that C35 tracks).
This document is the conformance assessment of that abstraction against the
COMPLETE ENG-183 Rev 5.0 design-rule document, not just the layer table.

## 1. Covered by the λ abstraction (layer rules 4.x) — with documented exceptions

All drawn-layer rules map onto SCMOS_SUBM values scaled by 0.2 µm; where the
native value is TIGHTER than the λ value, the entry is overridden in
`rules.yaml` and marked as an exception:

| # | Rule group | ENG-183 refs | Status |
| --- | --- | --- | --- |
| E1 | VIA1/VIA2/VIA3 fixed 0.5 µm | VIA1.W.1, VIA2.W.1, VIA3.W.1 | override (λ 2λ=0.4 too small) + area 0.25 |
| E2 | NPLUS/PPLUS overlap of DIFF 0.45 | NP.O.1, PP.O.1 | override (λ 4.2 = 0.40) |
| E3 | NPLUS/PPLUS enclosure of diffusion contacts 0.25 | CO.E.4, CO.E.3 | override (λ 4.3 = 0.20) |
| E4 | stacked vias allowed | VIA1.C.1, VIA2.C.1 | `stacked_vias: true` disables 8.4/14.4 |
| E5 | POLY2 (CPOLY) 0.8/0.65/1.2 | PO2.W.1, PO2.S.1, PO2.C.1, PO2.E.2 | native-aligned (λ looser) |
| E6 | bonding pad 85 µm | CB.W.1 | override (λ 10.1 = 60) |
| E7 | HRES to POLY1/DIFF 0.35, HRES to POLY2 3.0, HRES enc POLY2 3.0 | S1HRP1, S1DFHR, S1HRP2, E1HRP2 | added (λ highres rules do not cover POLY2) |

Rules that AGREE with λ values (no override): OD.S.1 (0.6), PO.C.1 (0.2),
OD.C.2/OD.C.4 (1.2), CO.C.2 (0.4), M2.W.1 (0.6), M3.W.1/M3.S.1 (0.6),
M4.W.1/M4.S.1 (0.6), M1.E.1-style enclosures, CO.W.1 (0.4 exact).

Active reference implementation scope is C35B4C3. The historical public
Calibre runset enables HRES for C3 and disables it in its O1 option branch;
Europractice's current 2026 process listing describes both C35B4C3 and
C35B4O1 as HR processes. O1 is deferred until that option conflict is
reconciled against a current kit. The thick-metal module (MET4 2.5/2.0,
R01M4) belongs to C35B4M3/M6 and is NOT modeled here.

## 2. NOT representable in the λ abstraction (must be handled separately)

These rule families are outside the SCMOS vocabulary. The native deck
(`reference/klayout/ams_c35_native.lydrc`) covers the layer rules; the items
below need dedicated checks or designer guidelines:

| Family | ENG-183 section | Examples | Handling |
| --- | --- | --- | --- |
| Density | 4.1.3/4.1.7-9/4.4.3 | PO.R.1 14 %, M1/M2/M3/M4.R.1 30 % | fill generation / density signoff |
| Antenna | 7.x | A.R.1-5 floating-layer area ratios (t1 thickness table) | antenna signoff (PERC) |
| Scribe border | 6.x | seal ring 10 µm, predefined SCRIBE | assembly guideline |
| Stress / CMP | 8.x | AMT top-metal dummies, AM metal slots (max width 35 µm) | assembly guideline |
| Latch-up | 9.x | LAT.1-9 guard rings; LAT.2 40 µm NMOS-PMOS (I/O); LAT.3 20 µm tap distance | guideline + I/O design rule |
| Element rules | 5.x | predefined CVAR/LAT2/NMOSH/VERT10 layouts; ND/NWD/PD diode usage; resistor corner correction (1/3 square per 90°) | per-element contracts |
| Guidelines | 5.2.4 etc. | NMOS_G2 min analog L 0.7 µm; RPOLYH_G2 high-precision width 2 µm; CPOLY_G1/G2 no PPLUS/NPLUS on CPOLY | designer guidelines |
| PAD element rules | 4.1.12/4.4.4 | CB.R.1 bond stack, PADVIA ratios 5 %, S1xPA 9 µm | pad cell signoff |

## 3. Practical meaning for siliconcraft

- The λ abstraction is a **geometry-manufacturability layer** for the drawn
  layers only; it stays valid for stdcell/analog layout of the core module.
- Density, antenna, stress and latch-up are **full-chip signoff concerns** —
  they belong to the fill/PERC/assembly flow, not the λ deck.
- For the RF path (ENG-188), the layout envelope is governed by the RF device
  contracts (finger width/count, gate-contact topology), not by λ — see
  `docs/ams_c35_rf.md` for the SCMOS_RF patch architecture.

## 4. C35B4C3 GDS stream map and fab gate

`profiles/ams_c35/gds_layer_map.yaml` records the C35B4 stream pairs from the
public `cac35b4rules_all.run` snapshot.  The core production masks are:

| AMS name | GDS layer/datatype |
| --- | ---: |
| NTUB / DIFF | 5/0, 10/0 |
| POLY1 / POLY2 | 20/0, 30/0 |
| NPLUS / PPLUS | 23/0, 24/0 |
| CONT | 34/0 |
| MET1 / VIA1 / MET2 / VIA2 | 35/0, 36/0, 37/0, 38/0 |
| MET3 / VIA3 / MET4 | 39/0, 41/0, 42/0 |
| PAD / HRES | 40/0, 29/0 |

Generated C35 routing labels use the AMS text streams `M1NET=61/22`,
`M2NET=61/23`, `M3NET=61/24`, `M4NET=61/25`, and `P1NET=61/21`; the old
generic `64/0` label layer and the AMI06-only `90/0` substrate helper are not
emitted for this profile.  The routing-probe and stdcell GDS exporters reject
any pair absent from the profile map.

The checked-in source is a pinned public HIT-Kit mirror, so the map is
**reference-validated, not fab-authoritative**.  CMC states that access to the
C35B4C3 kit and DRM is licensed, and that designs must be DRC-clean with the
current kit before fabrication.  Run:

```text
python3 scripts/validate_ams_c35_gds.py --profile ams_c35
```

For a layout artifact, run the same validator inside KLayout with `--gds`.
`--require-fab-authority` intentionally fails until the profile is replaced or
overlaid with the current licensed AMS/CMC stream map.  This prevents a public
historical map from being represented as a tapeout signoff.

## 5. Device contracts and module variants

`profiles/ams_c35/modules.yaml` exposes only the active engineering target,
`C35B4C3`: 4M/2P with PIP, the 5V gate option, and HRES. `C35B4O1` is
intentionally deferred; its current public Europractice option row lists HR
and an ARC photodiode in an EPI layer, while the historical runset disables
HRES in its O1 branch. Do not infer O1 HRES support from either source alone.
METCAP/CMIM and `ngatecap` remain disabled for this target; the historical
runset reports the in-well gate-cap structure as unsupported with no standard
size.

The public AMS Calibre runset defines these historical terminal contracts:

| Device | Extracted terminals | Recipe / status |
| --- | --- | --- |
| VERT10 | C, B, E | Three-terminal PNP; predefined layout, must not change |
| LAT2 | C, B, E, S, G | Five-terminal PNP; predefined 2 µm × 2 µm emitter, not checked by batch LVS |
| CVAR | G, S, D, B | Four-terminal MOS varactor; predefined unit layout |
| ZD2SM24 | POS, NEG, SUB | Fixed programming geometry for qualified zap blocks only |
| CPOLYRF | POS, NEG, SUB | Three-terminal RF poly capacitor |
| RDIFFP/RDIFFN | POS, NEG | Two-terminal diffusion resistors |
| RDIFFP3/RDIFFN3 | POS, NEG, SUB | Three-terminal diffusion resistors |
| RNWELL | 3-terminal JFET model class | GSA checklist classification; public layout diagram has two contacts, but model terminal geometry/card remain unavailable |

The historical runset maps ND/PD/NWD as parasitic diodes intended for
reverse-leakage and junction-capacitance simulation, not as active circuit
elements. ENG-183 depicts a two-contact n-well layout element, while the GSA
model checklist classifies RNWELL as a three-terminal JFET; the PCell geometry
is therefore layout-only and does not define the missing JFET pin map. NMOSH
and NMOSMH layouts are predefined; only W may change. These recipes are not
generated here.

The historical Calibre terminal names and maps remain metadata in
`profiles/ams_c35/devices/bindings.yaml`. The executable profile path now uses
`profiles/ams_c35/pcells.yaml`, `profiles/ams_c35/devices.yaml`, and the shared
authoritative LVS engine: C35 core/MIDOX MOS, resistor, PIP, and ND/PD/NWD
recognition are exercised by the generated fixture. The current fixture
contains 18 PCell variants and passes the public native DRC with zero markers.
The `diode_pn` PCell marks its full NTUB: extraction emits the PD junction and
the corresponding full-area NWD substrate parasitic. Neither diode model card
is present in the public model library.
The RPOLYH PCell passes this layer-rule DRC and shared-reference LVS smoke,
but the public PPLUS-to-derived-RPOLYH terminal spacing rule is not proven by
that layer deck. Do not treat RPOLYH geometry as signoff-validated.

This is reference engineering, not licensed-kit signoff. CPOLY and RPOLYH
cards are thesis-backed; RPOLY2 corners are user-supplied, with its POLY2
contact resistance still estimated. VERT10 has a source-backed typical PNP
card; LAT2, RNWELL JFET, and ND/PD/NWD numerical cards remain unavailable.
PNP physical-layout recognition remains contract-only, and xschem still
exposes core n/p MOS only.

The XH035 audit remains bounded to its existing eight MOS/HV/isolated/LDMOS
bindings; no non-MOS device support was inferred or added.

These sources bound the implementation to historical reference data:

- [CMC AMS Basic](https://www.cmc.ca/ams-350-nm-cmos-basic/) and
  [CMC AMS Opto](https://www.cmc.ca/ams-350-nm-cmos-opto/) describe C35B4C3
  and C35B4O1 product scope.
- [ENG-183 Rev 5.0](https://opencourses.emu.edu.tr/pluginfile.php/31894/mod_resource/content/1/Process%20Design%20Rules.pdf)
  is a 2005 historical design-rules copy.
- [AMS-authored public Calibre runset snapshot](https://raw.githubusercontent.com/jjwikner/daisy/c6d8341f36d734a55b9ac0902547744c93cd4cd6/daisy/pdk/ams035/pv/calibre/cac35b4rules_all.run)
  is a historical 2006.2 rule set, last modified in 2008; it is not the
  current licensed signoff deck.
- [CMC kit access requirements](https://www.cmc.ca/ams-0-35-%C2%B5m-design-kits/)
  require a site license and the current kit for fabrication signoff.

ams states its 2016 iPDK includes characterized models, Calibre/Assura
verification and extraction runsets, and PyCells
([announcement](https://ams-osram.com/news/press-releases/ams-releases-interoperable-pdk-for-its-0-35mm-analog-specialty-processes)).
No non-core model cards were recovered publicly or found in this repository.
Production PCells, simulation wrappers, and signoff LVS therefore require the
current licensed kit; historical public metadata is not tapeout authority.
