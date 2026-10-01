# Modular process capability architecture

This is the architecture boundary for extending the SCMOS geometry/device IR to
analog, RF, HV, power, opto, MEMS, ESD, and reliability.  It deliberately does
not define a monolithic `SCMOS_BCD` process.  A BCD offering is a composition of
capabilities with process-specific collateral.

## 1. Composition model

`SCMOS_CORE` remains the process-independent geometry and topology layer:

- normalized FEOL/BEOL layers, wells, implants, contacts, vias, and metals;
- lambda-scalable width/spacing/enclosure/overlap checks where the source rule
  actually scales;
- ordinary MOS, diode, resistor, and capacitor recognition;
- topology-level LVS and RC extraction.

Capabilities attach beside the core rather than subclassing it:

```text
SCMOS_CORE
├── SUBM / DEEP
├── ANALOG
├── RF
├── HV
├── ISOLATION
├── BIPOLAR
├── POWER
├── OPTO
├── MEMS
├── ESD
├── PASSIVE
└── RELIABILITY / THERMAL
```

A process profile declares capability state (`supported`, `partial`, `blocked`,
or `unavailable`) and owns the collateral for each state:

The Python ProcessIR keeps the two contracts separate:

- `physical_capabilities` describes what the process physically provides.  It
  is projected from legacy `meta.features` until a profile supplies explicit
  `meta.physical_capabilities`.
- `collateral_capabilities` describes tool and collateral readiness: DRC, LVS,
  models, xschem, PCell, and PEX topology/runtime/RC contracts.  CI gates use
  this object; it is not evidence that the process physically contains a
  feature.

```yaml
process: example_xh035
capabilities:
  hv: {state: supported}
  isolation: {state: partial, modes: [deep_nwell]}
  bipolar: {state: supported}
  power: {state: partial}
  opto: {state: supported}
  mems: {state: unavailable}
```

This is a target contract.  Existing flat `meta.features` flags remain the
compatibility input for the physical projection until profiles are migrated.
They are not silently treated as a complete stateful capability declaration;
explicit `meta.physical_capabilities` values take precedence.

Derived-layer and device-recognition expressions use the backend-neutral
`common.recognition` AST.  The AST supports boolean composition, geometric
relations, growth/shrink, holes, and an explicit backend callback for
connectivity.  KLayout compilation is a boundary adapter; no KLayout types
are part of ProcessIR.


`devices.yaml` remains a device table, not a capability table.  A device entry
must identify its recognition, terminals, LVS class, simulation model, and
extraction level.  A capability may expose zero or many devices.

## 2. Extraction levels and device origin

Every special or parasitic device should declare two orthogonal properties:

```yaml
device:
  class: special
  type: diode
  origin: parasitic       # intentional | parasitic
  extraction:
    level: lumped         # none | lumped | distributed | field_solver
```

`origin` controls promotion policy.  A parasitic junction or BJT may be
ignored, warned, extracted, or promoted to an intentional device without
changing its geometric recognition.  `extraction.level` controls the backend
and output contract:

- `none`: geometry/ERC only;
- `lumped`: scalar or compact SPICE parameters;
- `distributed`: network extraction such as substrate RC or RLCG;
- `field_solver`: mesh and solver results, with provenance and convergence
  metadata.

The common recognition output should be a device graph.  RCX, parasitic-device,
substrate, EM, thermal, optical, and mechanical extractors consume that graph;
none of them should re-parse foundry GDS independently.

## 3. MEMS capability (`SCMOS_MEMS`)

SCMOS MEMS option layers are a mask-level entry point, not a complete MEMS
process.  The minimum normalized recognition vocabulary is:

```text
MEMS_OPEN
MEMS_ETCH_STOP
MEMS_ANCHOR
MEMS_STRUCTURAL
MEMS_SACRIFICIAL
MEMS_CAVITY
MEMS_BACKSIDE       optional
MEMS_ELECTRODE      usually poly or metal
```

MEMS requires a process stack in addition to lambda geometry:

```yaml
mems:
  layers:
    structural: ...
    sacrificial: ...
    anchor: ...
    cavity: ...
  process:
    release_direction: top | bottom | both
    etch_depth_um: ...
    sidewall_angle_deg: ...
    undercut_um: ...
  material:
    silicon:
      thickness_um: ...
      density_kg_m3: ...
      young_modulus_pa: ...
      poisson_ratio: ...
      residual_stress_pa: ...
```

Values are mandatory before mechanical simulation; no generic SCMOS defaults
are valid.  The flow is separate from PEX:

```text
GDS / PCell
  ├─ DRC
  ├─ topological LVS
  └─ process-stack reconstruction
       └─ 3-D geometry → mesh → multiphysics
            └─ reduced-order model → SPICE / Verilog-A
```

Call this extraction `MEX` (mechanical extraction).  Its result schema should
carry mass, stiffness, resonant modes, Q/damping assumptions, electrode
capacitance, `dC/dx`, pull-in voltage, thermal resistance, and thermal
expansion, each with units and provenance.  Gmsh/Elmer are backends, not part
of the SCMOS geometry contract.  Palace remains an RF/EM backend.

Current repository state: MEMS layers are not enabled in a materialized profile;
therefore no MEMS rules, process stack, MEX, or model are claimed.

## 4. Opto capability (`SCMOS_OPTO`)

Photodiodes are intentional semiconductor devices, not ordinary diode aliases.
The minimum layout vocabulary is:

```text
PHOTO_DIODE
OPTICAL_WINDOW
PHOTO_GUARD
PHOTO_ACTIVE
SALICIDE_BLOCK       optional
```

A device contract must identify the junction topology independently of the
physical option names:

```yaml
photodiode:
  junction: pplus_nwell
  terminals: [anode, cathode]
  geometry:
    area: extracted
    perimeter: extracted
  electrical:
    dark_current: empirical_or_model
    junction_capacitance: model
    breakdown_voltage: model
    series_resistance: model
  optical:
    active_area: extracted
    optical_window: required
    responsivity_vs_wavelength: model_or_table
    quantum_efficiency: model_or_table
  noise:
    shot_noise: derived
    dark_noise: model_or_measurement
```

The first usable implementation should be electrical photodiode extraction plus
an empirical responsivity parameter.  Full optical generation and carrier
transport are optional escalations:

```text
GDS / PCell → junction geometry
                 ├─ optical model → generation profile
                 └─ DEVSIM electrical transport
                         └─ responsivity / Cj / Idark / bandwidth
                              └─ compact model
```

Meep-to-DEVSIM coupling belongs in the opto backend contract and must not be
required by ordinary LVS.  No photodiode capability is currently materialized
in this repository; XH profile HVCMOS support must not be interpreted as
photodiode support without explicit layers, models, and optical collateral.

## 5. RF capability

RF is a horizontal capability, not a process node.  At minimum it needs
separate recognition and model identity for:

```text
RF_NMOS / RF_PMOS
RF_HV_NMOS / RF_HV_PMOS
VARACTOR
RF_MIM
MOM
INDUCTOR
TRANSFORMER
TL_MICROSTRIP / TL_CPW / TL_GCPW / TL_DIFF
RF_KEEP_OUT / RF_NO_FILL / RF_NO_QRC
```

RF MOS geometry must preserve topology that DC MOS extraction can collapse:

```yaml
rf:
  enabled: true
  gate_contact: single | double | distributed
  body_contact: {type: ..., distance_um: ...}
  source_drain: {shared_diffusion: true}
  nqs: true
  model: rf_model_name
```

Equal total width does not imply equal RF behavior: finger count, gate
contact topology, body-contact distance, shared diffusion, and layout symmetry
affect `Rg`, `Rb`, access resistance, capacitance, and NQS behavior.

RF passives require absolute, stack-dependent geometry and models.  An
inductor/transformer contract should include turns, width, spacing, diameter,
metal stack, underpass, shield, center tap, and model representation
(lumped/S-parameter/vector-fit).  A transmission line produces frequency-
dependent `R(f), L(f), C(f), G(f)` rather than only RC.

Extraction escalation:

```text
RCX → substrate RC → quasistatic RL/K → full-wave EM
       ├─ FastHenry / electrostatic backend
       └─ Palace or openEMS backend
                         └─ S-parameters → vector fit / compact model
```

Via and contact arrays need an RF model contract (`R`, `L`, `C`, array/current
crowding policy); `R/N` is only a DC fallback.  RF no-fill/keep-out markers are
recognition inputs and must survive into signoff metadata.

No RF models or EM stack should be inferred from ordinary SCMOS lambda rules.
The existing RF work is profile-specific and remains separate from this
SCMOS extension status table until collateral exists.

The conservative L0 RF workbench receives frequency and die limits through
`common.rf.policy.PROJECT_RF_POLICY` or an explicit caller policy.  Its report
records the selected policy; those limits are analysis-envelope choices, not
process capability claims.

## 6. Parasitic and special devices

Use one `SPECIAL_DEVICE` contract for intentional and derived devices.  Examples:

```text
DIODE / PARASITIC_DIODE
BJT / PARASITIC_BJT
SCHOTTKY / ZENER
LDMOS / DMOS / RESURF
VARACTOR / RF_MIM / MOM
INDUCTOR / TRANSFORMER / TLINE
PHOTODIODE / PIN / APD / SPAD
ESD_DIODE / SCR
```

Recognition should be an intermediate derived layer, not necessarily a foundry
GDS layer:

```text
foundry layers → canonical layer IR → DEVICE_RECOG → device graph
```

The recognition namespace can be typed as:

```text
MOS, RF_MOS, BJT, PARASITIC_BJT, DIODE, PARASITIC_DIODE,
LDMOS, VARACTOR, MIM, MOM, INDUCTOR, TRANSFORMER, TLINE,
PHOTODIODE, MEMS, ESD
```

This lets latch-up, ESD, and substrate analysis promote a parasitic BJT without
pretending it is an intentional symbol.  The device graph must retain origin,
recognition source, terminal semantics, model provenance, and extraction level.

## 7. Lambda boundary and BCD composition

Lambda abstraction is appropriate for normalized CMOS geometry, much of the
metal/via stack, and basic wells.  It becomes insufficient or only a geometry
pre-check for:

| Boundary | Required contract |
| --- | --- |
| thick oxide | capability plus absolute rule and model |
| LDMOS drift / RESURF | device-specific geometry and model |
| deep/triple well, DTI, SOI/BOX | isolation topology and absolute process data |
| photodiode/window/APD/SPAD | junction, optical, electrical, and noise models |
| MEMS release | process stack, materials, etch and undercut |
| RF inductor/T-line | stack-dependent EM geometry and frequency model |
| thermal/reliability/ESD | current, temperature, field, and failure criteria |

Therefore:

- HVCMOS is primarily HV + isolation, with optional power/passive/device
  capabilities.
- BCD is a composition of HV + isolation + bipolar + power + passive +
  reliability; it is not a universal lambda rule family.
- XH-like sensor/HV processes may compose HV + bipolar + opto + passive without
  becoming BCD.
- SOI BCD additionally requires explicit BOX/DTI/isolation collateral.

`λ_FEOL` and `λ_BEOL` remain useful for geometry normalization.  They must not
be used to synthesize process stacks, voltage ratings, optical data, RF models,
or mechanical material properties.

## 8. Implementation order

1. Keep legacy `meta.features` as compatibility input, but expose physical
   capability projections separately from `collateral_capabilities` in
   `ProcessIR`; explicit `meta.physical_capabilities` values override inferred
   projections.
2. Use the backend-neutral `common.recognition` AST for derived layers and
   device recognition.  Compile it through explicit backend adapters; never
   infer electrical connectivity from geometric interaction.
3. Expand the canonical catalog with structural diode, resistor, capacitor,
   BJT, tap, RF-passive, ESD, and fuse families.  Profiles add bindings only
   when recognition, model, LVS, and extraction collateral exists.
4. Keep MOS voltage, oxide, threshold, channel, gate-stack, and isolation
   attributes orthogonal.  Preserve `well_type` and `isolation_domain` only as
   compatibility fallbacks while topology records become authoritative.
5. Use `stack_v2` for ordered semiconductor/conductor/dielectric/via data.
   Missing cross-section, material, or model evidence remains unavailable; no
   lambda default may fill it.
6. Keep RF frequency/die limits in an explicit analysis policy, not in
   `ProcessIR` or physical capability claims.  Add RF/ESD/power/special-device
   collateral validators only alongside source evidence.
## 9. Canonical device contract

The canonical catalog is structural vocabulary, not process support. A composed
`ProcessIR` keeps three roles separate:

- `device_inventory`: the profile's grouped legacy/source-backed device table;
- `device_bindings`: the profile's layout, simulation, and LVS binding records;
- `canonical_catalog`: shared family definitions and terminal variants.

Binding records may supply `canonical_attributes`, but the loader rejects every
key not declared by the referenced family. Terminal variants carry the complete
canonical terminal list; backend-specific `simulation` and `lvs` maps/orders are
validated independently. This is required for body/substrate, shield, Kelvin,
four-terminal HBT, and substrate-referenced passive devices.

Geometry contracts declare one of `fixed`, `scalable`, `enumerated`, or
`derived`. MOS and RF MOS share the same width semantics: `w` is per physical
finger, `nf` is the physical finger count, `m` is electrical multiplicity, and
`total_width`/`effective_width` are normalized explicitly. Parameter transforms
support rename, scale/multiply, divide, derive, and ignore without evaluating
arbitrary code; simulation and LVS transform sequences are independent.

## 10. Recognition, capability, and external oracles

Recognition complements require a named `universe_source`. Physical growth and
shrink quantize non-zero distances conservatively to at least one DBU;
`touch` is strict edge/point contact and does not match positive-area overlap.
Invalid layer names and non-positive DBU values fail at the IR boundary.

`well_topology` records legacy bulk/well topology. `advanced_isolation` records
deep-well, twin-well, isolated-domain, or explicitly declared isolation modes.
The compatibility `isolation` key refers to advanced isolation only. CMOS and
special-device capability projections use effective bindings and inventory;
catalog membership alone is never evidence of process support.

`common.devices.gf180_device_oracle` and
`common.devices.sg13g2_device_oracle` are thin, manifest-driven adapters.
They require an operator-provisioned official artifact root and compare
canonical terminal/attribute observations. No GF180MCU or IHP SG13G2 PDK facts,
model numbers, ports, or geometry constants are embedded in SiliconCraft.
