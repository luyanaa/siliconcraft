"""Row-level transistor geometry for standard-cell layouts.

The analog MOS PCells remain available for standalone devices.  This module
materializes a standard-cell transistor row as one active/select/well/poly/
contact shape plan so shared diffusion is a row property, not a bridge between
independent MOS instances.
"""

from dataclasses import dataclass
import math
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class RowShape:
    layer: str
    x0: float
    y0: float
    x1: float
    y1: float
    net: str | None
    purpose: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "layer": self.layer,
            "x0": self.x0,
            "y0": self.y0,
            "x1": self.x1,
            "y1": self.y1,
            "net": self.net,
            "purpose": self.purpose,
        }


@dataclass(frozen=True)
class DiffusionBay:
    x0: float
    x1: float
    y0: float
    y1: float
    net: str
    contacted: bool
    contact_x: float
    device: str
    index: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "x0": self.x0,
            "x1": self.x1,
            "y0": self.y0,
            "y1": self.y1,
            "net": self.net,
            "contacted": self.contacted,
            "contact_x": self.contact_x,
            "device": self.device,
            "index": self.index,
        }


@dataclass(frozen=True)
class TransistorRow:
    polarity: str
    y_um: float
    active: tuple[RowShape, ...]
    select: tuple[RowShape, ...]
    wells: tuple[RowShape, ...]
    gates: tuple[RowShape, ...]
    contacts: tuple[RowShape, ...]
    diffusion_bays: tuple[DiffusionBay, ...]
    labels: tuple[tuple[str, float, float], ...]
    device_order: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "polarity": self.polarity,
            "y_um": self.y_um,
            "device_order": list(self.device_order),
            "active": [shape.as_dict() for shape in self.active],
            "select": [shape.as_dict() for shape in self.select],
            "wells": [shape.as_dict() for shape in self.wells],
            "gates": [shape.as_dict() for shape in self.gates],
            "contacts": [shape.as_dict() for shape in self.contacts],
            "diffusion_bays": [bay.as_dict() for bay in self.diffusion_bays],
            "labels": [list(label) for label in self.labels],
        }


def _contact_count(process, active_height: float) -> tuple[int, float, float]:
    tech = process.tech
    pitch = tech.contact_size + tech.contact_spacing
    usable = active_height - 2 * tech.active_contact_enc
    count = max(1, int(math.floor((usable + tech.contact_spacing) / pitch + 1e-9)))
    height = count * tech.contact_size + (count - 1) * tech.contact_spacing
    if height > usable + 1e-9:
        raise ValueError("diffusion contact stack exceeds active containment")
    bottom = -active_height / 2.0 + tech.active_contact_enc + (usable - height) / 2.0
    return count, height, bottom


def _contact_bay_bounds(placement, index: int) -> tuple[float, float, float]:
    footprint = placement.footprint
    active_left = placement.x_um - footprint.active_width_um / 2.0
    active_right = placement.x_um + footprint.active_width_um / 2.0
    contacts = tuple(placement.x_um + value for value in footprint.contact_xs_um)
    gates = tuple(placement.x_um + value for value in footprint.gate_xs_um)
    gate_left = gates[0] - placement.length_um / 2.0
    gate_right = gates[-1] + placement.length_um / 2.0
    if index == 0:
        return active_left, gate_left, contacts[0]
    if index == placement.nf:
        return gate_right, active_right, contacts[-1]
    return (
        gates[index - 1] + placement.length_um / 2.0,
        gates[index] - placement.length_um / 2.0,
        contacts[index],
    )


def _bay_net(placement, index: int) -> str:
    left = placement.left_net or placement.device.drain
    right = placement.right_net or placement.device.source
    return left if index % 2 == 0 else right


def build_transistor_row(
    process,
    polarity: str,
    device_order: Sequence[str],
    placements: Mapping[str, Any],
) -> TransistorRow:
    """Build one row from ordered placements and their contacted bays."""
    ordered = tuple(placements[name] for name in device_order)
    if not ordered:
        raise ValueError(f"{polarity}: cannot build an empty transistor row")
    tech = process.tech
    active: list[RowShape] = []
    select: list[RowShape] = []
    wells: list[RowShape] = []
    gates: list[RowShape] = []
    contacts: list[RowShape] = []
    bays: list[DiffusionBay] = []
    labels: list[tuple[str, float, float]] = []
    shared_active: list[RowShape] = []
    y = ordered[0].y_um
    select_enc = tech.select_channel_enc
    for placement in ordered:
        half_w = placement.footprint.active_width_um / 2.0
        half_h = placement.footprint.active_height_um / 2.0
        active.append(
            RowShape(
                "ACTIVE",
                placement.x_um - half_w,
                y - half_h,
                placement.x_um + half_w,
                y + half_h,
                None,
                "row_active",
            )
        )
        select.append(
            RowShape(
                "PSELECT" if polarity == "p" else "NSELECT",
                placement.x_um - half_w - select_enc,
                y - half_h - select_enc,
                placement.x_um + half_w + select_enc,
                y + half_h + select_enc,
                None,
                "row_select",
            )
        )
        for index, gate_x in enumerate(placement.footprint.gate_xs_um):
            gates.append(
                RowShape(
                    "POLY",
                    placement.x_um + gate_x - placement.length_um / 2.0,
                    y - half_h - placement.footprint.gate_extension_um,
                    placement.x_um + gate_x + placement.length_um / 2.0,
                    y + half_h + placement.footprint.gate_extension_um,
                    placement.device.gate,
                    "gate",
                )
            )
        contact_count, contact_height, contact_bottom = _contact_count(
            process, placement.footprint.active_height_um
        )
        for bay_index in range(placement.nf + 1):
            x0, x1, contact_x = _contact_bay_bounds(placement, bay_index)
            bay_left, bay_right = sorted((x0, x1))
            contact_half = tech.contact_size / 2.0
            if (
                contact_x - contact_half < bay_left - 1e-9
                or contact_x + contact_half > bay_right + 1e-9
                or y + contact_bottom < y - half_h - 1e-9
                or y + contact_bottom + contact_height > y + half_h + 1e-9
            ):
                raise ValueError(
                    f"{placement.device.name}: diffusion contact bay {bay_index} "
                    "does not contain its contact stack"
                )
            side = "left" if bay_index == 0 else "right" if bay_index == placement.nf else None
            contacted = side not in set(placement.contactless_sides)
            net = _bay_net(placement, bay_index)
            bays.append(
                DiffusionBay(
                    min(x0, x1),
                    max(x0, x1),
                    y - half_h,
                    y + half_h,
                    net,
                    contacted,
                    contact_x,
                    placement.device.name,
                    bay_index,
                )
            )
            if not contacted:
                continue
            for row_index in range(contact_count):
                cy = y + contact_bottom + row_index * (tech.contact_size + tech.contact_spacing)
                contacts.append(
                    RowShape(
                        "CC",
                        contact_x - tech.contact_size / 2.0,
                        cy,
                        contact_x + tech.contact_size / 2.0,
                        cy + tech.contact_size,
                        net,
                        "diffusion_contact",
                    )
                )
            contacts.append(
                RowShape(
                    "M1",
                    contact_x - tech.contact_size / 2.0 - tech.metal_contact_enc,
                    y + contact_bottom - tech.metal_contact_enc,
                    contact_x + tech.contact_size / 2.0 + tech.metal_contact_enc,
                    y + contact_bottom + contact_height + tech.metal_contact_enc,
                    net,
                    "diffusion_contact_landing",
                )
            )
            labels.append((net, contact_x, y))

    for left, right in zip(ordered, ordered[1:]):
        left_right = left.right_net or left.device.source
        right_left = right.left_net or right.device.drain
        if left_right != right_left:
            continue
        x0 = left.x_um + left.footprint.active_width_um / 2.0
        x1 = right.x_um - right.footprint.active_width_um / 2.0
        if x1 <= x0:
            continue
        half_h = min(left.footprint.active_height_um, right.footprint.active_height_um) / 2.0
        shared_active.append(
            RowShape("ACTIVE", x0, y - half_h, x1, y + half_h, left_right, "shared_diffusion")
        )
        shared_active.append(
            RowShape(
                "PSELECT" if polarity == "p" else "NSELECT",
                x0 - select_enc,
                y - half_h - select_enc,
                x1 + select_enc,
                y + half_h + select_enc,
                left_right,
                "shared_diffusion_select",
            )
        )

    active.extend(shape for shape in shared_active if shape.layer == "ACTIVE")
    select.extend(shape for shape in shared_active if shape.layer != "ACTIVE")
    if polarity == "p":
        min_x = min(shape.x0 for shape in active)
        max_x = max(shape.x1 for shape in active)
        well_height = max(process.row_height_um("p"), tech.nwell_min_width + 2 * tech.nwell_active_enc)
        wells.append(
            RowShape(
                "NWELL",
                min_x - tech.nwell_active_enc,
                y - well_height / 2.0,
                max_x + tech.nwell_active_enc,
                y + well_height / 2.0,
                "VDD",
                "row_well",
            )
        )
    return TransistorRow(
        polarity,
        y,
        tuple(active),
        tuple(select),
        tuple(wells),
        tuple(gates),
        tuple(contacts),
        tuple(bays),
        tuple(labels),
        tuple(device_order),
    )
