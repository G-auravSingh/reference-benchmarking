# Metric Registry and Extensibility

The registry is the scientific contract for an indicator. A calculator must not hard-code scoring or applicability decisions that belong in the registry.

Each indicator records, at minimum:

- name and domain;
- pillar and ecological subdimension;
- ecological question;
- units and direction;
- evidence tier and source type;
- reference requirement/type;
- scoring role;
- proxy/measured status;
- uncertainty method;
- project aggregation method;
- management use and limitations.

## Adding a future field indicator

A camera-trap occupancy, acoustic diversity, vegetation structure, soil, water chemistry or other field-derived indicator can be registered without changing the aggregation engine. It must, however, satisfy the production gates before becoming score-eligible:

1. ecological relevance is documented;
2. measurement protocol and effort are defined;
3. QA/QC is available;
4. direction/response function is defensible;
5. a valid reference/comparator exists;
6. uncertainty is represented;
7. applicability to the ecological domain is explicit;
8. redundancy with existing indicators is assessed.

Without the comparator, the observation remains contextual/baseline evidence.

## Redundancy principle

Three versions of the same greenness signal should not become three independent votes simply because they are separate columns. New indicators must be assigned to an ecological subdimension and reviewed for complementarity before being activated for scoring.
