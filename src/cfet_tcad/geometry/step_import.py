"""STEP (CAD) import: mesh a .step assembly into an MSH 2.2 file the
``structure: external`` pipeline can consume.

A STEP file carries B-rep geometry only - no mesh, no physical groups,
no TCAD semantics - so the conversion is driven by a mapping spec (YAML):

.. code-block:: yaml

    step_file: device.step     # relative to the spec file's directory
    unit_cm: 1.0e-7            # required: 1 CAD unit = this many cm
    mesh_size: 2.0             # characteristic length, CAD units
    mesh_size_per_region: {gox: 0.5}         # optional
    regions:                   # every volume must be claimed exactly once
      bulk: {select: {label: ".*silicon.*"}, material: Silicon}
      gox:  {select: {volume: 2},            material: Oxide}
    contacts:                  # surface selectors (bbox, CAD units)
      source: {select: {bbox: [0, 0, 0, 0, 5, 3]}, region: bulk}
    interfaces:                # shared faces are found automatically
      si_ox: [bulk, gox]

Units: OpenCASCADE's ~1e-7 geometric tolerance collides with nm-sized
devices expressed in cm, so import and meshing happen in the CAD's own
coordinates; the finished mesh is then scaled to cm with a pure node
transform (``affineTransform``), which never touches OCC.
"""

import re
from dataclasses import dataclass
from pathlib import Path

import gmsh


@dataclass
class VolumeInfo:
    tag: int
    label: str
    bbox: tuple  # (x0, y0, z0, x1, y1, z1) in CAD units


def _volume_table(volumes: list[VolumeInfo]) -> str:
    lines = ["  tag  label / bbox [CAD units]"]
    for v in volumes:
        lo = ", ".join(f"{c:.6g}" for c in v.bbox[:3])
        hi = ", ".join(f"{c:.6g}" for c in v.bbox[3:])
        lines.append(f"  {v.tag:>3}  {v.label or '(unnamed)'}   "
                     f"[{lo}] -> [{hi}]")
    return "\n".join(lines)


def _collect_volumes() -> list[VolumeInfo]:
    out = []
    for dim, tag in gmsh.model.getEntities(3):
        bbox = tuple(gmsh.model.getBoundingBox(dim, tag))
        out.append(VolumeInfo(tag=tag, label=gmsh.model.getEntityName(dim, tag),
                              bbox=bbox))
    return out


def discover_step(step_path: Path) -> list[VolumeInfo]:
    """Import a STEP file and list its volumes (tag, CAD label, bbox) -
    the reference table users need to write a mapping spec."""
    step_path = Path(step_path)
    if not step_path.exists():
        raise FileNotFoundError(f"STEP file not found: {step_path}")
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("step_discover")
        gmsh.model.occ.importShapes(str(step_path))
        gmsh.model.occ.synchronize()
        return _collect_volumes()
    finally:
        gmsh.finalize()


def _boxes(name: str, value) -> list[list[float]]:
    """Normalize a bbox selector: one box (6 numbers) or a list of
    boxes whose matches are united - contacts like a GAA gate need
    several thin slabs to pick the shell's lateral faces without the
    axial end rings."""
    if value and isinstance(value[0], (list, tuple)):
        boxes = [[float(x) for x in b] for b in value]
    else:
        boxes = [[float(x) for x in value]]
    for b in boxes:
        if len(b) != 6:
            raise ValueError(f"'{name}': every bbox needs 6 numbers "
                             f"[x0,y0,z0,x1,y1,z1], got {len(b)}")
    return boxes


def _tags_in_boxes(boxes: list[list[float]], eps: float,
                    dim: int) -> set[int]:
    found: set[int] = set()
    for b in boxes:
        found |= {t for _d, t in gmsh.model.getEntitiesInBoundingBox(
            b[0] - eps, b[1] - eps, b[2] - eps,
            b[3] + eps, b[4] + eps, b[5] + eps, dim=dim)}
    return found


def _bbox_tolerance(bbox: tuple) -> float:
    """Selector boxes are typed by hand: pad them by a small fraction of
    the model diagonal so exact-face coordinates are caught reliably."""
    dx = bbox[3] - bbox[0]
    dy = bbox[4] - bbox[1]
    dz = bbox[5] - bbox[2]
    return 1e-3 * max(dx, dy, dz, 1.0)


def _select_volumes(name: str, select: dict, volumes: list[VolumeInfo],
                    eps: float) -> list[int]:
    if not isinstance(select, dict) or len(select) != 1:
        raise ValueError(
            f"region '{name}': select needs exactly one of "
            f"label / volume / bbox, got {select!r}")
    (kind, value), = select.items()
    if kind == "label":
        rx = re.compile(str(value))
        tags = [v.tag for v in volumes if v.label and rx.search(v.label)]
    elif kind == "volume":
        wanted = [int(value)] if not isinstance(value, list) else \
            [int(x) for x in value]
        known = {v.tag for v in volumes}
        bad = [t for t in wanted if t not in known]
        if bad:
            raise ValueError(f"region '{name}': volume tag(s) {bad} do not "
                             f"exist; volumes are:\n{_volume_table(volumes)}")
        tags = wanted
    elif kind == "bbox":
        tags = sorted(_tags_in_boxes(_boxes(f"region {name}", value),
                                      eps, dim=3))
    else:
        raise ValueError(f"region '{name}': unknown selector '{kind}' "
                         f"(use label / volume / bbox)")
    if not tags:
        raise ValueError(f"region '{name}': selector {select!r} matched no "
                         f"volume; volumes are:\n{_volume_table(volumes)}")
    return tags


def _region_boundary(region_tags: list[int]) -> set[int]:
    faces = gmsh.model.getBoundary([(3, t) for t in region_tags],
                                   combined=False, oriented=False)
    return {t for _d, t in faces}


def convert_step(spec: dict, spec_dir: Path, out_msh: Path) -> dict:
    """Mesh a STEP file into MSH 2.2 with the physical groups the external
    pipeline needs.  Returns a summary dict (regions/contacts/interfaces
    with their entity counts) for logging."""
    spec_dir = Path(spec_dir)
    out_msh = Path(out_msh)

    step_file = Path(spec.get("step_file") or "")
    if not step_file.is_absolute():
        step_file = spec_dir / step_file
    if not step_file.exists():
        raise FileNotFoundError(f"STEP file not found: {step_file}")
    try:
        unit_cm = float(spec["unit_cm"])
    except (KeyError, TypeError, ValueError):
        raise ValueError(
            "unit_cm is required: 1 CAD unit expressed in cm "
            "(nm -> 1.0e-7, um -> 1.0e-4, mm -> 1.0e-1)") from None
    regions_spec = spec.get("regions") or {}
    if not regions_spec:
        raise ValueError("spec has no regions - run discovery (--list) "
                         "first, then map every volume to a region")
    contacts_spec = spec.get("contacts") or {}
    interfaces_spec = spec.get("interfaces") or {}
    mesh_size = float(spec.get("mesh_size") or 0)

    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("step_import")
        imported = gmsh.model.occ.importShapes(str(step_file))
        gmsh.model.occ.synchronize()
        # labels vanish on fragment children: capture them up front
        parent_labels = {tag: gmsh.model.getEntityName(3, tag)
                         for d, tag in imported if d == 3}

        # boolean-fragment the assembly: multi-solid STEP files are not
        # conformal, and only shared faces mesh conformally (a DEVSIM
        # requirement for interfaces and touching regions)
        vols = gmsh.model.getEntities(3)
        _out, out_map = gmsh.model.occ.fragment(vols, [])
        gmsh.model.occ.synchronize()
        for (d, parent), children in zip(vols, out_map):
            label = parent_labels.get(parent, "")
            if not label:
                continue
            for cd, child in children:
                if cd == 3 and not gmsh.model.getEntityName(3, child):
                    gmsh.model.setEntityName(3, child, label)

        volumes = _collect_volumes()
        model_bbox = tuple(gmsh.model.getBoundingBox(-1, -1))
        eps = _bbox_tolerance(model_bbox)

        # resolve region selectors; every volume claimed exactly once
        region_tags: dict[str, list[int]] = {}
        claimed: dict[int, str] = {}
        for name, rspec in regions_spec.items():
            tags = _select_volumes(name, rspec.get("select") or {},
                                   volumes, eps)
            for t in tags:
                if t in claimed:
                    raise ValueError(
                        f"volume {t} claimed by both '{claimed[t]}' and "
                        f"'{name}'; volumes are:\n{_volume_table(volumes)}")
                claimed[t] = name
            region_tags[name] = tags
        unclaimed = [v for v in volumes if v.tag not in claimed]
        if unclaimed:
            raise ValueError(
                f"volume(s) {[v.tag for v in unclaimed]} not claimed by any "
                f"region - every volume needs an owner; volumes are:\n"
                f"{_volume_table(volumes)}")

        for name, tags in region_tags.items():
            gmsh.model.addPhysicalGroup(3, tags, name=name)

        # contacts: bbox surface selectors, restricted to faces that
        # actually bound the declared owner region AND are exterior -
        # faces shared with another region are interfaces, and a bbox
        # around a whole gate-oxide shell must not swallow the
        # silicon-oxide interface underneath it
        boundaries = {r: _region_boundary(t) for r, t in region_tags.items()}
        for name, cspec in contacts_spec.items():
            owner = cspec.get("region")
            if owner not in region_tags:
                raise ValueError(f"contact '{name}': region '{owner}' is "
                                 f"not defined in regions")
            select = cspec.get("select") or {}
            if list(select) != ["bbox"]:
                raise ValueError(f"contact '{name}': contacts support the "
                                 f"bbox selector only, got {select!r}")
            boxes = _boxes(f"contact {name}", select["bbox"])
            found = _tags_in_boxes(boxes, eps, dim=2)
            shared = set().union(*(b for r, b in boundaries.items()
                                   if r != owner))
            faces = sorted(found & (boundaries[owner] - shared))
            if not faces:
                raise ValueError(
                    f"contact '{name}': bbox {boxes} matched no face of "
                    f"region '{owner}' (tolerance {eps:.3g}); check the "
                    f"coordinates against the volume table:\n"
                    f"{_volume_table(volumes)}")
            gmsh.model.addPhysicalGroup(2, faces, name=name)

        # interfaces: shared faces between the two regions' volumes
        for name, pair in interfaces_spec.items():
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                raise ValueError(f"interface '{name}': needs [regionA, "
                                 f"regionB], got {pair!r}")
            a, b = pair
            for r in (a, b):
                if r not in region_tags:
                    raise ValueError(f"interface '{name}': region '{r}' is "
                                     f"not defined in regions")
            shared = sorted(boundaries[a] & boundaries[b])
            if not shared:
                raise ValueError(
                    f"interface '{name}': regions '{a}' and '{b}' share no "
                    f"face - are the solids actually touching?")
            gmsh.model.addPhysicalGroup(2, shared, name=name)

        if mesh_size > 0:
            gmsh.model.mesh.setSize(gmsh.model.getEntities(0), mesh_size)
        for name, size in (spec.get("mesh_size_per_region") or {}).items():
            if name not in region_tags:
                raise ValueError(f"mesh_size_per_region: unknown region "
                                 f"'{name}'")
            pts = gmsh.model.getBoundary(
                [(3, t) for t in region_tags[name]], combined=False,
                oriented=False, recursive=True)
            gmsh.model.mesh.setSize([p for p in pts if p[0] == 0],
                                    float(size))

        gmsh.model.mesh.generate(3)
        # scale CAD units -> cm as a pure node transform (post-meshing,
        # so OCC never sees cm-scale coordinates)
        s = unit_cm
        gmsh.model.mesh.affineTransform([s, 0, 0, 0,
                                         0, s, 0, 0,
                                         0, 0, s, 0])
        out_msh.parent.mkdir(parents=True, exist_ok=True)
        gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
        gmsh.write(str(out_msh))

        return {
            "volumes": volumes,
            "regions": {n: len(t) for n, t in region_tags.items()},
            "contacts": list(contacts_spec),
            "interfaces": list(interfaces_spec),
            "nodes": len(gmsh.model.mesh.getNodes()[0]),
        }
    finally:
        gmsh.finalize()


def starter_external_config(spec: dict, out_msh: Path) -> dict:
    """A runnable ``structure: external`` config skeleton for the
    converted mesh.  Doping defaults to a mild uniform profile on every
    silicon region - the user tunes doping / workfunctions / biases.

    The simulation type is picked from the contact names: a CFET stack
    (contacts split into ``*_n`` and ``*_p`` sub-devices) gets a
    ``cfet_idvg`` sweep with per-sub-device polarity/workfunctions, so
    the starter actually runs; a single device gets a plain ``idvg``.
    A single-device idvg needs contacts literally named source/drain/
    gate, so mismatched names would otherwise crash on a missing
    ``drain`` - the CFET branch avoids that for stacked geometries."""
    regions = {name: r.get("material", "Silicon")
               for name, r in (spec.get("regions") or {}).items()}
    contacts = {name: c["region"]
                for name, c in (spec.get("contacts") or {}).items()}
    silicon = [n for n, m in regions.items() if m == "Silicon"]
    doping = {n: {"profile": "uniform", "donors_cm3": 1.0e17,
                  "acceptors_cm3": 0.0} for n in silicon}
    external = {
        "mesh_file": Path(out_msh).name,  # sits next to the config
        "dimension": 3,
        "regions": regions,
        "contacts": contacts,
        "interfaces": {k: list(v) for k, v in
                       (spec.get("interfaces") or {}).items()},
        "doping": doping,
    }

    is_cfet = (any(c.endswith("_n") for c in contacts)
               and any(c.endswith("_p") for c in contacts))
    if is_cfet:
        # infer per-sub-device polarity / gate metal from the _n/_p suffix
        external["silicon_polarity"] = {
            n: ("p" if n.endswith("_p") else "n") for n in silicon}
        gates = [n for n, r in contacts.items()
                 if regions.get(r) == "Oxide"]
        external["gate_workfunctions"] = {
            g: (4.72 if g.endswith("_p") else 4.50) for g in gates}
        simulation = {"type": "cfet_idvg", "vdd": 0.7, "vg_start": 0.0,
                      "vg_stop": 0.7, "vg_step": 0.05}
    else:
        simulation = {"type": "idvg", "vd": [0.05], "vg_start": 0.0,
                      "vg_stop": 0.7, "vg_step": 0.1}

    return {
        "device": {
            "name": Path(out_msh).stem,
            "structure": "external",
            "polarity": "n",
            "gate_workfunction_ev": 4.5,
            "external": external,
        },
        "simulation": simulation,
        "output": {"directory": f"results/{Path(out_msh).stem}",
                   "vtk": True},
    }
