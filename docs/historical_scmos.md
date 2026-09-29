# Historical SCMOS process research

This document records the historical SCMOS families requested for siliconcraft. It is a reference contract, not an active foundry PDK. The machine-readable source is [`schema/historical_scmos_process_matrix.yaml`](../schema/historical_scmos_process_matrix.yaml).

## Decision

Merge the public evidence as:

- a provenance-backed process/capability matrix;
- logical-layer and MOSIS option metadata;
- separate standard, tight-metal, and SUBM rule overlays;
- historical Magic PEX method and representative coefficient snapshots;
- regression checks that prevent accidental promotion to an active profile.

Do **not** merge these sources as complete calibrated device models, signoff DRC, signoff LVS, or signoff PEX. Existing active AMI16/HP06 manifests remain source-driven and authoritative for their current scope.

## Process mapping

| Historical family | Lambda | MOSIS mapping | Capabilities captured | Magic evidence | Limit |
| --- | ---: | --- | --- | --- | --- |
| Orbit 2.0 | 1.0 um | `SCNA`, `SCNE`, `SCN`, `SCNA_MEMS` | analog, vertical NPN, buried CCD, electrode/poly2, floating gate, MEMS | Bundled `SCNA20(ORB)` / `SCPE20(ORB)` extraction styles; `SCNA_MEMS.80.tech27` feature grammar | Archive `SCNA.80` is labeled `AMIabn`, so it is not an exact Orbit PEX target |
| AMI ABN 1.2 | 0.6 um | `SCNA`, `SCNE`, `SCN`; HV | analog/NPN, buried CCD, electrode/poly2, high voltage | MOSIS mapping; archive `SCNA.80` is a generic `AMIabn` 1.6 um/lambda-0.8 style | No exact 1.2 um Magic target located |
| HP CMOS34 / AMOSI | 0.6 um | `SCNLC`, `SCN`; tight-metal | LC/cap-well, tight-metal | Bundled `SCN12LC(HP)` under the `TIGHTMETAL` branch; `scmos-tm.tech` lambda-0.6 family | No exact 2002a process-specific file located |
| AMI CWL | 0.5 um | `SCNPC`; tight-metal | poly capacitor (`POLY_CAP1`/`CPC`), tight-metal | Logical `polycap` layer contract | No exact AMI CWL/`SCNPC` Magic target file located |
| HP CMOS26B historical 3M | 0.5 um | `SCN3M` | 3M; unusually rich Magic PEX | Bundled `SCN08(HP)`; MOSIS run `n33h`; full resistance/contact/capacitance/device directives | 2001a/2002a `SCN3M.50.tech27` header says `HPcmos26g`, so B/G names are preserved rather than normalized |
| HP CMOS26G | 0.5 um | `SCN3M`, `SCN`; tight-metal | 3M, tight-metal, rich PEX | `SCN3M.50.tech27`, header `HPcmos26g` | The bundled lambda-0.5 `SCN08(HP)` branch is separately labeled CMOS26B |
| HP CMOS26G SUBM | 0.4 um | `SCN3M_SUBM`, `SCN_SUBM` | 3M, SUBM, fill, stacked-via grammar, rich PEX | `SCN3M_SUBM.40.HP.tech27`, header `HPcmos26g`; bundled `SCN08(HP26G)` | Historical data; not an active calibrated profile |
| HP MOS14TB | 0.35 um | `SCN3M`, `SCN`, `SCN3MLC`, `SCNLC` | 3M, LC/cap-well, silicide-block contract | `SCN3M.35.tech27`, `SCN3MLC.35.tech27`, header `HPcmos14tb` | CMOS14 exact-contact/array rule must be retained |
| HP MOS14TB SUBM | 0.3 um | `SCN3M_SUBM`, `SCN_SUBM`, `SCN3MLC_SUBM`, `SCNLC_SUBM` | 3M, SUBM, LC, silicide-block, fill/stacked-via grammar | `SCN3M_SUBM.30.tech27`, `SCN3MLC_SUBM.30.tech27` | CMOS14 exact-contact/array rule must be retained |
| HP GMOS10QA | 0.25 um | `SCN4N`; tight-metal | 4M, tight-metal | MOSIS mapping and logical 4M contract | No exact GMOS10QA/`SCN4N` Magic target file located |
| HP GMOS10QA SUBM | 0.2 um | `SCN4M_SUBM`; tight-metal | 4M, SUBM, tight-metal | `SCN4M_SUBM.20.tech27` supplies 4M/SUBM backend grammar | Archive header says `TSMC35`; it is method-only, not GMOS10QA coefficients |

The `HP CMOS26B`/`HP CMOS26G` distinction is deliberate. The old bundled source explicitly documents `SCN08(HP)` as “HP CMOS26B 1.0 micron”, while the archive `SCN3M.50.tech27` header says `HPcmos26g`. A clean alias would erase evidence and could select the wrong extraction constants.

## Magic release separation

Magic's catalog describes three different things:

1. **Archive release 2001a.** A separate historical release.
2. **Archive release 2002a.** The last known MOSIS SCMOS release in the catalog.
3. **Bundled `scmos.tech`.** The standard scalable-CMOS distribution and its source `profiles/ls1u/reference/magic/scmos.tech.in`.

They must not be treated as aliases. The archive techfiles have `version 2001a` or `version 2002a` headers and target-specific filenames. The bundled source has its own historical conditional branches and an older distribution history. In particular:

- archive `SCNA.80.tech27` / `SCNA_MEMS.80.tech27` are labeled `AMIabn`; they expose generic analog/MEMS grammar, while `SCNA.80` is 1.6 um/lambda-0.8 and is not an exact AMI ABN 1.2 or Orbit target;
- bundled `SCNA20(ORB)` is the exact historical location for Orbit 2.0 analog/BJT extraction data;
- bundled `SCN12LC(HP)` is the exact historical location for HP CMOS34 linear-cap extraction data;
- bundled `SCN08(HP)` is the exact historical location for the requested HP CMOS26B rich 3M extraction data;
- archive `SCN3M_SUBM.40.HP.tech27` and the HP MOS14TB `SCN3M`/`SCN3MLC` files have target labels matching the corresponding HP family;
- archive `SCN4M_SUBM.20.tech27` is a TSMC35-labeled 4M/SUBM backend, not a GMOS10QA process file.

The distribution decks also encode different contracts: `scmos-tm.tech` is the tight-metal family, `scmos-sub.tech` is the HP CMOS26G/CMOS14B SUBM family, `scmosWR.tech` avoids routes through wells, and `scmos.tech` is the standard scalable family.

## Layer and rule abstractions

The sources expose a useful two-level contract:

- **Logical SCMOS options:** E/electrode, A/analog, 3M/4M, LC/cap-well, PC/poly-cap, MEMS, and SUBM.
- **Physical output identifiers:** for example `POLY_CAP1` GDS 28/CPC, `SILICIDE_BLOCK` GDS 29/CSB, `PBASE` GDS 58/CBA, `BURIED_CCD` GDS 57/CCD, `CAP_WELL` GDS 59/CWC, `VIA2` GDS 61/CVS, `METAL3` GDS 62/CMT, `VIA3` GDS 30/CVT, and `METAL4` GDS 31/CMQ.

Feature-specific handling is not interchangeable:

- Orbit analog/NPN/CCD/floating-gate/MEMS requires `pbase`, emitter/collector semantics, buried-CCD layers, electrode/poly2, and MEMS open/etch-stop layers.
- HP CMOS34 uses the LC/cap-well path (`SCNLC`, `CWC`), not the poly-cap path.
- AMI CWL uses `SCNPC`, `POLY_CAP1`, and `CPC`; it must not be modeled as `SCNLC`.
- HP MOS14TB's CMOS14 contact policy is exact standard contact/via sizes plus arrays for large openings.
- GMOS10QA is mapped to 4M/SUBM option vocabulary only until a target-specific Magic/output source is found.

The extracted tight-metal and SUBM overlays are kept separate from the current normalized rule families. They are evidence for future profile work, not a silent modification of active NCSU profiles.

## Historical Magic PEX method

The reusable abstraction is the **shape of the extraction contract**, not an unqualified copy of all coefficients:

- `planeorder` defines layer precedence;
- `resist` defines sheet resistance in Magic's milliohm/square convention;
- `contact` defines contact resistance, with old bundled styles using milliohm/contact and newer files using Magic-native contact syntax;
- `areacap`, `overlap`, `perimc`, `sideoverlap`, and `sidewall` define parasitic terms in Magic's lambda-scaled capacitance conventions;
- `fet` and `fetresis` define device extraction and channel-resistance methods;
- `device` directives cover special capacitors and the Orbit NPN;
- `sidehalo`, fill planes, and stacked-contact directives affect geometry/connectivity behavior.

The old PEX blocks are unusually rich for the HP CMOS26B/26G and HP MOS14TB families. Representative source snapshots are stored in the matrix, including:

- Orbit `SCNA20(ORB)`, MOSIS run `n34o`, lambda 100 centimicron;
- HP CMOS34 `SCN12LC(HP)`, run `n36y`, lambda 60;
- HP CMOS26B `SCN08(HP)`, run `n33h`, lambda 50;
- HP CMOS26G SUBM `SCN08(HP26G)`, run `n48r`, lambda 40;
- 2002a HP CMOS26G SUBM and HP MOS14TB standard/SUBM extraction styles.

Comments such as `MODEL HANDLES THIS` are ownership boundaries. Intrinsic MOS gate and junction terms must not be duplicated in PEX when the compact model owns them. This matches siliconcraft's existing source-driven PEX separation: a Magic deck can supply geometry/connectivity grammar while coefficients remain explicitly sourced and validated.

## SCMOS PEX priority ladder

The active PEX profiles follow a lot-consistent sourcing policy: device model,
sheet resistance, capacitance, and contact/via resistance must come from the
same MOSIS run before a profile is promoted beyond partial RC. AMI16 (N88Z)
meets that bar end-to-end; AMI06 (N8BN) and HP06 (N8AG) source contact/via
resistance from their reports, while sheet/capacitance coefficients still come
from the NCSU CDK branches (an aggregate that can mix runs) and are withheld
from junction/substrate terms. The full four-point audit (SPICE / PEX-RC /
field stack / benchmark) per flow is in
[`process_flow_audit.md`](process_flow_audit.md).

Planned expansion order (priority, process, MOSIS run, status):

| Priority | Process / run | Role | Status |
| --- | --- | --- | --- |
| A+ | AMI C5N / N8BN | first PEX/stdcell timing baseline | active, first-hand contact/via in manifest |
| A+ | HP AMOS14TB / N8AG | silicided-process cross-check | active, first-hand contact/via in manifest |
| A+ | HP GMOS10QA / N88W 0.35 µm | SUBM scaling, 4M routing | local first-hand verified (RO 176.09 MHz); profile not yet assembled |
| A+ | TSMC035 3M / N88Y 0.35 µm | SUBM + TSMC cross-check | local first-hand verified (non-silicided, RO 196.17 MHz); T27K is a separate silicided run — never merged |
| A+ | TSMC025 / N94S 0.25 µm | SUBM vs DEEP abstraction experiment | local first-hand verified; no RO in report → derived inverter-chain benchmark |
| A | AMI CWL / N87R ~1 µm | early SCMOS benchmark | local first-hand verified (RO 110.33 MHz); profile not yet assembled |
| A | AMI ABN / N88Z ~1.2–1.6 µm | old-node PEX benchmark | active (ami16 profile) |
| A-/A | Orbit / N91W 2 µm | early SCMOS / 2M benchmark | local first-hand verified (RO 36.62/40.24 MHz); profile not yet assembled |
| A-/A | TSMC018 / T28M | DEEP lower bound, 6M | first-hand archived in-repo (docs/mosis_evidence/); MOS+RC pairing complete (report carries its own BSIM3 cards) |
| B/C | HP CMOS26G / CMOS34 | historical compatibility | no clean lot-level complete source yet |
| — | ams C35 / SCN4ME_SUBM (λ=0.2) | 0.35 µm mixed-signal, manufacturable | ACTIVE profile: ENG-183 exceptions recorded (VIA 0.5, select/active 0.45, N+/P+ enc 0.25); ENG-188 RF model contract; cards NDA |
| — | CNM25 (IMB-CNM APDK) | 2.5 µm academic, SCMOS-covering | ACTIVE profile: SCMOS-conservative + native DRC abstractions; FastCap C / FastHenry R-L flow prepared |

Rules that apply before any of these become active profiles:

- the first-hand MOSIS parametric report (or a verified mirror) must be read,
  not a downstream summary; NCSU `layerDefinitions.tf` aggregates can mix runs
  (AMI_C5N via/via2 match T01X, HP_AMOS14TB sheet values cite N98R/N74K);
- the run must match the shipped model cards (AMI06 N8BN, HP06 N8AG, AMI16
  N88Z, HP10 N88W, TSMC035 N88Y, TSMC025 N94S);
- N94S is the highest-value near-term target: with SUBM (λ=0.15) and DEEP
  (λ=0.12) overlays on the same electrical process, the generator can measure
  the design-rule-abstraction penalty directly.

## SCMOS 7.2 device extensions (defined / DRC+LVS / λ)

The three-way feasibility analysis for the SCMOS 7.2 option device families
(HVCMOS, electrode capacitor/transistor, vertical NPN, linear capacitor,
buried CCD, silicide-block resistor, MEMS, SCNPC) lives in
[`scmos72_device_extensions.md`](scmos72_device_extensions.md); the
machine-readable `option_rule_families` registry is part of the matrix
schema. Status summary:

| Family | Defined | λ rules | DRC | LVS |
| --- | :-: | :-: | :-: | :-: |
| Electrode capacitor (11) | ✅ | ✅ | implemented | implemented |
| Electrode transistor (12) | ✅ | ✅ | implemented | implemented |
| Electrode contact (13) | ✅ | ✅ | implemented | implemented |
| Vertical NPN (16) | ✅ | ✅ | implemented (Magic); siliconcraft gap | implemented |
| Linear capacitor (17/18) | ✅ | ✅ | implemented (Magic); siliconcraft gap | implemented |
| Buried CCD (19) | ✅ | ✅ | implemented (Magic); siliconcraft gap | not applicable |
| Silicide block (20) | ✅ | ✅ | lambda_only | recipe |
| SCNPC POLY_CAP1 (23) | ✅ | ✅ | lambda_only | none |
| HVCMOS (CVP/CVN) | ✅ (layers) | ❌ | none (override-gated) | partial (CDK tactive) |
| MEMS (COP/CPS) | ✅ (layers) | ❌ | none | none |

HVCMOS and MEMS are the only two families without official SCMOS 7.2 λ
rules: HV is an undeclared option with marker layers only and **no λ rules
are implemented by default** — applying the process-specific Magic
`scmos.tech.in` AMI 1.5 µm 20.x set requires an explicit `hvcmosLambdaOverride`
feature opt-in, enforced by `common/process_ir.py`; MEMS is explicitly
unregulated by Magic with only micrometer-level process guidelines
(NIST IR 5402, MOSIS newsletter 206).

## Sources

- [MOSIS SCMOS 7.2 PDF](https://www.clear.rice.edu/elec422/1999/manual/mosis_scmos7_2.pdf)
- [Southampton SCMOS 8.0 notes](https://personal.southampton.ac.uk/~bim/notes/ice/DesignRules/scmos-main.html)
- [Magic SCMOS technology catalog](https://opencircuitdesign.com/magic/tech.html)
- [Magic 2001a archive](https://opencircuitdesign.com/magic/archive/2001a.tar.gz)
- [Magic 2002a archive](https://opencircuitdesign.com/magic/archive/2002a.tar.gz)

Field-stack evidence (first-hand foundry thickness for two ladder families,
archived in this repo): TSMC018 stack from `T-018-MM-SP-001` Table 10.1
([`docs/mosis_evidence/t018mms001_table10-1.md`](mosis_evidence/t018mms001_table10-1.md));
TSMC035 cross-section from the TSMC035 design-rules deck
([`docs/mosis_evidence/tsmc035_cross_section.md`](mosis_evidence/tsmc035_cross_section.md)).
The AMI (C5N/CWL/ABN) and HP (AMOS14TB/GMOS10QA) families have no first-hand
thickness in any public source; the full search log is in
[`docs/mosis_evidence/ami_hp_field_search.md`](mosis_evidence/ami_hp_field_search.md)
(only numeric anchor found: AMI C5N polysilicon 0.4 µm from a NIST journal
paper). All such stacks must be `derived` (see
[`process_flow_audit.md`](process_flow_audit.md)).

The repository's bundled historical source is [`profiles/ls1u/reference/magic/scmos.tech.in`](../profiles/ls1u/reference/magic/scmos.tech.in). Its values are retained as historical reference snapshots and are not asserted to be current foundry calibration.
