# Darukaa Site Selection → Adaptive Biodiversity Assessment Handoff

## Contract

The preferred production input is the standardized Site Selection handoff. A project manifest identifies the project; a tile manifest identifies the EMUs; each tile contains the EMU geometry and attributes.

The native Site Selection tile-manifest fields supported by the adaptive parser are:

- `project_name`
- `n_tiles`
- `tile_paths`
- `tile_labels`

The parser also accepts the package's normalized `tiles`, `emus` or GeoJSON feature-list forms for interoperability.

## EMU requirements

Every EMU must resolve to:

- unique `emu_id`;
- valid geometry;
- optional domain (`terrestrial`, `aquatic`, `mixed`/`auto`);
- optional parent zone;
- optional source attributes;
- computed area.

Multipart/disconnected geometry is valid. It must not be exploded into multiple ecological units unless the upstream handoff explicitly defines those as separate EMUs.

## Domain routing

The project may be terrestrial, aquatic or mixed. In a mixed project, domain is resolved at EMU level when supplied. Aquatic and terrestrial reference populations remain separate.

## Input validation

The parser fails explicitly for missing/ambiguous tile paths, duplicate EMU IDs or invalid geometries. It does not infer scientific meaning from filenames.
