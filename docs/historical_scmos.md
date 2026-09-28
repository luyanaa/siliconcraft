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

## Sources

- [MOSIS SCMOS 7.2 PDF](https://www.clear.rice.edu/elec422/1999/manual/mosis_scmos7_2.pdf)
- [Southampton SCMOS 8.0 notes](https://personal.southampton.ac.uk/~bim/notes/ice/DesignRules/scmos-main.html)
- [Magic SCMOS technology catalog](https://opencircuitdesign.com/magic/tech.html)
- [Magic 2001a archive](https://opencircuitdesign.com/magic/archive/2001a.tar.gz)
- [Magic 2002a archive](https://opencircuitdesign.com/magic/archive/2002a.tar.gz)

The repository's bundled historical source is [`profiles/ls1u/reference/magic/scmos.tech.in`](../profiles/ls1u/reference/magic/scmos.tech.in). Its values are retained as historical reference snapshots and are not asserted to be current foundry calibration.
