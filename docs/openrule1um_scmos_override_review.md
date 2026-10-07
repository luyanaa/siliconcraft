# OpenRule1um vs SCMOS: override review

Status: **analysis only — no policy change made.** This document exists so the
override design can be reviewed before any rule value is committed.

## Why this is a question at all

OpenRule1um is a de-documented abstraction of PTC06. The expectation recorded in
the profile is that PTC06 sits close to SCMOS / SCMOS_SUBM, so the profile
chooses a **SCMOS lambda envelope as its base** and then overrides it with values
from the native deck. The open question is whether those overrides are chosen
consistently.

## What the profile already declares

`profiles/openrule1um/rules.yaml` → `rules.portable`:

```yaml
policy: scmos_lambda_envelope
lambda_um: 0.5
scmos_variant: non_submicron          # the classic (non-submicron) SCMOS arm
base_source: common/drc/scmos_reference.py
target_drc: reference/drc.lydrc
well_tightenings:
  - {id: OR1-WELL-SPACE,  layer: nwell,          base_um: 4.5, value_um: 5.0}
  - {id: OR1-WELL-NDIFF,  layer: nwell, layer2: nactive, base_um: 2.5, value_um: 3.0}
beol:
  policy: native_override
  rules:  # M1/M2/M3 width and spacing all 1.0; via marker spacings 0.5
nominal_geometry: {contact_cut_um: 1.0, via1_cut_um: 1.0, via2_cut_um: 1.0}
```

So the declared policy is: **SCMOS non_submicron envelope, with native values
substituted wherever the native deck is stricter.**

## The two sources, mechanically derived

SCMOS non_submicron values come from the `else:` arm of
`common/drc/scmos_reference.py` (the `if submicron or deep:` branch), scaled by
`lambda_um = 0.5`. Native values come from
`profiles/openrule1um/reference/drc.lydrc`, at the line numbers the profile
cites.

| semantic rule | SCMOS non-submicron @ λ=0.5 | OpenRule1um native | stricter | declared/expected |
| --- | --- | --- | --- | --- |
| active.min_width | 3λ = 1.50 | `diff.width(1.0)` = 1.00 | SCMOS 1.50 | SCMOS |
| poly.min_width | 2λ = 1.00 | `pol.width(1.0)` = 1.00 | tie 1.00 | 1.00 |
| nwell.min_width | 10λ = 5.00 | `nwl.width(4.0)` = 4.00 | SCMOS 5.00 | SCMOS |
| nwell spacing (diff potential) | 9λ = 4.50 | `nwl.space(5.0)` = 5.00 | native 5.00 | **native 5.00** (OR1-WELL-SPACE) |
| nwell–ndiff spacing | 5λ = 2.50 | `nwl.separation(ndiff,3.0)` = 3.00 | native 3.00 | **native 3.00** (OR1-WELL-NDIFF) |
| metal.M1.min_width | 3λ = 1.50 | `ml1.width(1.0)` = 1.00 | native 1.00 | **native 1.00** |
| metal.M1.min_spacing | 2λ = 1.00 | `ml1.space(1.0)` = 1.00 | tie 1.00 | 1.00 |
| metal.M2.min_width | 3λ = 1.50 | `ml2.width(1.0)` = 1.00 | native 1.00 | **native 1.00** |
| metal.M2.min_spacing | 3λ = 1.50 | `ml2.space(1.0)` = 1.00 | native 1.00 | **native 1.00** |
| metal.M3.min_width | 6λ = 3.00 | `ml3.width(1.0)` = 1.00 | native 1.00 | **native 1.00** |
| metal.M3.min_spacing | 4λ = 2.00 | `ml3.space(1.0)` = 1.00 | native 1.00 | **native 1.00** |
| via1 / via2 spacing | 3λ = 1.50 | `dm_via1.space(0.5)` = 0.50 | native 0.50 | **native 0.50** |
| contact cut size | 2λ = 1.00 | nominal geometry 1.00 | tie 1.00 | 1.00 |

Every row the profile declares as a native override is genuinely **the stricter
of the two**, and every row it leaves alone is a case where the SCMOS envelope is
already the stricter (or equal) value. So the declared policy is internally
consistent and conservative: **no rule is loosened relative to either source.**

## The one thing worth deciding

The policy is safe, but "safe" and "reasonable" are not the same question here.
Two observations to weigh:

1. **M3 is where the two sources diverge most.** SCMOS non_submicron wants M3 at
   6λ = 3.0µm wide / 4λ = 2.0µm spaced, because in the classic SCMOS stack M3 is
   a thick top metal. OpenRule1um's native M3 is an ordinary 1.0µm metal. Taking
   the native 1.0 is conservative against *both* decks, but it means the SCMOS
   envelope contributes nothing at M3 — the row geometry is driven entirely by
   the native deck there.

2. **The well tightenings are not semantic-key rules.** `OR1-WELL-SPACE` (1.2)
   and `OR1-WELL-NDIFF` (nwell/nactive) are native tightenings of SCMOS well
   spacing, but neither maps onto a key the stdcell/PCell consumers read (they
   read `nwell.min_width` and `nwell.active_enclosure`, both of which stay on the
   SCMOS value). So today those two tightenings affect the DRC envelope but not
   generated geometry.

## Options

- **A. Keep the declared policy as-is.** Derive `rules.stdcell.rule_map` from the
  "stricter of the two" column above, with each entry citing either the CDK rule
  id (SCMOS arm) or the native deck line (override). Fully sourced, no design
  change.
- **B. Change the policy first.** e.g. decide that where the native deck is
  *looser* than SCMOS the native value should win (that would loosen M3 to 1.0 —
  which is what A already does, since native is stricter), or that the SCMOS
  envelope should not apply to BEOL at all. This is a judgement about PTC06's
  lineage, not something derivable from the two decks.

Nothing in this document has been applied to `rules.yaml`.
