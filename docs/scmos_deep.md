# SCMOS DEEP profiles

Siliconcraft has two explicit SCMOS_DEEP profiles:

| Profile | CDK source | MOSIS option | λ (µm) | grid (µm) | minimum L/W (µm) | metal stack |
| --- | --- | --- | ---: | ---: | ---: | --- |
| `tsmc025_deep` | `TSMC_CMOS025_DEEP` / `tsmc_03d.tf` | `SCN5M_DEEP` | 0.12 | 0.06 | 0.24 / 0.36 | 5M, DEEP_N_WELL |
| `tsmc018_deep` | `TSMC_CMOS018_DEEP` / `tsmc_02d.tf` | `SCN6M_DEEP` | 0.09 | 0.045 | 0.18 / 0.27 | 6M, DEEP_N_WELL |

The profile metadata is sourced from the NCSU CDK `globalData.il`, technology files,
`divaDRC.rul`, public model cards, and the SCMOS stream/layer tables. The generated
layer contracts preserve the MOSIS physical name `DEEP_N_WELL`; the DRC/LVS runner
also exposes the lower-case semantic alias `deep_nwell` required by the shared
reference extractor.

## What is implemented

- `meta.rule_family: scmos_deep` is a distinct ProcessIR family. A DEEP process or
  MOSIS identifier cannot be loaded as ordinary `scmos_subm`, and `scmos_deep`
  cannot be used without a DEEP identifier.
- The shared reference DRC implements the DEEP rule deltas in the source deck,
  including the 5M/6M backend branches, stacked vias, and DEEP_N_WELL layer.
- Optional metal-cap and wide-metal rule sections that are absent from the
  source reference implementation are not claimed. Foundry density, antenna,
  fill, and signoff checks are also outside this profile contract.
- The reference LVS extractor recognizes the core `nmos4`/`pmos4` device contract.
- Public NCSU MOS model cards are generated under each profile. These cards are
  simulation/LVS model inputs only; their presence does not make PEX calibrated.
- `--deck auto` selects the shared reference DRC/LVS path. The profile rules files
  intentionally use `engine: scmos_reference`, so the generator fails closed rather
  than emitting an incomplete authoritative deck.

These are source-backed reference profiles, not foundry signoff PDKs. The rules
files and manifests set `signoff: false`, and no DEEP profile exposes generated
Magic PEX.

## PEX and field-solver decision

Generated TSMC Magic PEX remains deferred. The public DEEP model cards and
layer grammar do not by themselves supply a lot-matched extraction deck.
`tsmc018_deep` now has an external `field_solver_estimated` sweep contract
using the archived T-018-MM-SP-001 6M stack, but its contact/via, substrate,
exact T28M deviation, and calibration terms remain blocked. `tsmc025_deep`
has neither a run-matched public BEOL fit nor a field-solver profile. Do not
infer TSMC PEX from the model prefix, node name, or technology-file geometry.
The source-specific PEX boundary is tested by
`scripts/test_profile_collateral_matrix.py`.

For non-TSMC SCMOS families, the search and source audit is recorded in
[`schema/scmos_legacy_pex_audit.yaml`](../schema/scmos_legacy_pex_audit.yaml).
The important distinction is:

- AMI C5N (`ami06`), HP AMOS14TB (`hp06`), and AMI ABN (`ami16`) already have
  source-driven PEX manifests. Their remaining gaps are explicit in the manifests;
  no internet-derived replacement coefficients were copied over the run evidence.
- Orbit, HP CMOS34, HP CMOS26B/26G, and HP MOS14TB have historical Magic extraction
  blocks with sheet resistance, contacts, and capacitance terms. Those blocks are
  useful source references, but they are not promoted to active profiles without a
  matching layer map, device/model bindings, and fixture validation.
- HP GMOS10QA has a MOSIS option mapping and backend grammar references, but no exact
  target Magic/PEX source. It remains historical reference only.

## Reuse boundary through 130 nm

`scmos_deep` is not a generic “small lambda” switch. A future 130 nm or other DEEP
profile requires its own evidence for all of the following:

1. process-table entry and MOSIS option identifier;
2. stream/layer map, including available metal/via/deep-well layers;
3. DRC and extraction rule source (`divaDRC.rul`, `divaEXT.rul`, or an equivalent
   public/native deck);
4. device model cards and canonical device bindings;
5. source-specific regression fixtures for DRC, LVS, and any PEX coefficients.

Until those artifacts exist, a process is not enabled by copying the 0.18 or 0.25
profile and changing lambda. This avoids silently applying TSMC or generic SCMOS
assumptions to another foundry.

## Public sources consulted

- [MOSIS SCMOS rules mirror](https://www.fceia.unr.edu.ar/eca1/files/LDCI/Reglas_%20de_Diseno_MOSIS.pdf): DEEP option mappings, layer identifiers, and the DEEP rule columns.
- [Southampton SCMOS notes](https://www.southampton.ac.uk/~bim/notes/ice/DesignRules/scmos-main.html): logical layer/options and historical SCMOS rule context.
- [MOSIS SCMOS 7.2 mirror](https://www.ece.rice.edu/Courses/422/manual/mosis_scmos7_2.pdf): historical SCMOS option and layer reference.
- [Magic SCMOS source mirror](https://fossies.org/linux/magic/scmos/scmos.tech.in): historical technology branches and extraction-method context.
- [Magic HP CMOS26B extraction source](http://www.ittc.ku.edu/EECS/EECS_546/magic/files/techfiles/scmosExt26b.tech): an explicit historical non-TSMC sheet/contact/capacitance example; it is not silently treated as a current foundry calibration.
- [AMI C5N design-rule mirror](https://cag-uconn.github.io/courses/ece3421_s13/SN05_Rules.pdf): AMI layer map and SCMOS option rule context.
- [MOSIS submission database mirror](https://research.ece.cmu.edu/~mems/intranet/mosis-run/submit_data.html): historical process/run naming cross-check.

The exact coefficients used by siliconcraft remain tied to the local NCSU CDK and
archived MOSIS report files listed by each manifest. Public web rules establish
geometry and historical extraction grammar; they do not, by themselves, establish
current lot-specific PEX calibration.
