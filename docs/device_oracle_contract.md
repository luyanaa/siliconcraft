# External device-oracle contract

SiliconCraft does not embed GF180MCU or IHP SG13G2 PDK facts. The two thin
adapters are:

- `common.devices.gf180_device_oracle`
- `common.devices.sg13g2_device_oracle`

Each adapter reads an operator-provisioned artifact root. The root contains a
named manifest (`gf180_device_oracle.yaml` or `sg13g2_device_oracle.yaml`) and
an observations document. The manifest must include:

```yaml
oracle: gf180             # or sg13g2
source:
  kind: external
  artifact: /official/output/archive
  revision: official-revision-or-hash
cases:
  - id: device-case
    canonical_family: mos4
    terminals: [d, g, s, b]
    terminal_order: [d, g, s, b]
observations: observations.yaml
```

`source.artifact` and `source.revision` are provenance fields, not URLs or
embedded process claims. `observations` is the output of the official PCell,
test-GDS, or LVS workflow. The harness checks canonical family, terminal set
and order, optional backend terminal maps, attributes, and geometry fields.
Unexpected or missing cases fail; a missing external root raises
`OracleUnavailable` instead of becoming a false pass.

Environment variables for the normal adapters:

```text
SILICONCRAFT_GF180_ORACLE_ROOT
SILICONCRAFT_SG13G2_ORACLE_ROOT
```

The repository test `scripts/test_device_oracles.py` uses temporary structural
artifacts only to exercise the parser and negative mismatch path. It does not
claim that those artifacts are GF180MCU or SG13G2 data. Actual foundry-oracle
runs require the corresponding licensed/provisioned external root.
