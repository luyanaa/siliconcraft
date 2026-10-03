"""Runtime helpers shared by Magic PEX and RF workbench entry points."""

from __future__ import annotations

from pathlib import Path
import subprocess


FATAL_LOG_MARKERS = (
    "Error loading technology",
    "contained errors:",
    "Unknown layer/datatype",
    "Label on unknown layer/datatype",
    "Unrecognized section name",
    "Can't have overlap capacitance",
    "Only one of \"overlap ",
)


def run_magic_extract(
    magic: str,
    layout: Path,
    technology: Path,
    output: Path,
    workdir: Path,
    style: str,
    ignored_fatal_markers: tuple[str, ...] = (),
    top_cell: str | None = None,
    extract_resistance: bool = False,
) -> tuple[str, str]:
    """Run the existing layout -> Magic -> ext2spice PEX flow.

    The caller owns interpretation of the extracted netlist.  This function
    enforces the same fatal-log and output-file checks used by the PEX smoke
    gates.  A legacy technology may legitimately report unsupported optional
    GDS layers; those markers can be explicitly ignored while the caller still
    requires the expected extracted devices.  Resistance extraction is
    opt-in because most existing profile smokes only exercise MOS/C behavior.
    """
    cell = top_cell or layout.stem
    if layout.suffix.lower() == ".mag":
        commands = [
            f"load {layout}",
            "select top cell",
        ]
    else:
        commands = [
            f"gds read {layout}",
            f"load {cell}",
            "select top cell",
        ]
    extract_path = workdir / "extfiles"
    if extract_resistance:
        extract_path.mkdir(parents=True, exist_ok=True)
        flat_cell = f"{cell}_pex_flat"
        commands.extend(
            [
                f"flatten {flat_cell}",
                f"load {flat_cell}",
                f"cellname delete {cell}",
                f"cellname rename {flat_cell} {cell}",
                "select top cell",
                f"extract path {extract_path}",
            ]
        )
    commands.extend(
        [
            f"extract style {style}",
            "extract do capacitance",
            "extract do coupling",
        ]
    )
    if extract_resistance:
        commands.extend(
            [
                "extract do unique",
                "extresist threshold 10000",
            ]
        )
    commands.append("extract all")
    if extract_resistance:
        commands.append("extresist all")
    commands.extend(
        [
            "ext2spice format ngspice",
            "ext2spice subcircuit top on",
            "ext2spice cthresh 0",
            "ext2spice rthresh 0",
        ]
    )
    if extract_resistance:
        commands.append("ext2spice extresist on")
        commands.append(f"ext2spice -p {extract_path} -o {output}")
    else:
        commands.append(f"ext2spice -o {output}")
    commands.append("quit -noprompt")
    proc = subprocess.run(
        [magic, "-dnull", "-noconsole", "-T", str(technology)],
        input="\n".join(commands) + "\n",
        cwd=workdir,
        text=True,
        capture_output=True,
        check=False,
    )
    log = proc.stdout + proc.stderr
    if proc.returncode != 0:
        raise RuntimeError(f"Magic exited {proc.returncode}\n{log}")
    fatal = [
        marker
        for marker in FATAL_LOG_MARKERS
        if marker not in ignored_fatal_markers and marker in log
    ]
    if fatal:
        raise RuntimeError(f"Magic reported fatal extraction markers {fatal}\n{log}")
    if not output.exists():
        raise RuntimeError(f"Magic did not write {output}\n{log}")
    return output.read_text(), log
