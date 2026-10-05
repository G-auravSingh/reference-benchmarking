# v1.1.0 Full Build Validation

Build target: `darukaa_adaptive_v1.1.0`

Source:
- generalized v1.1.0 package
- attached `darukaa_reference_v0.2.7` source as authoritative legacy calculator implementation

Validation:
- pytest: 52 passed
- compileall: passed
- legacy live registrations: 46
- migrated FULL_INDICATORS: 46
- unique migrated names: 46
- release ZIP integrity: passed
- clean extraction/import: passed
- release SHA256: recorded in the delivery message and independently reproducible with SHA-256

Important:
- GitHub was not modified by this build.
- This build has not been run against Google Earth Engine in this environment.
- A live GEE/Colab Tata Motors run remains the deployment acceptance test.
- Missing external asset/dependency inputs are represented as explicit statuses rather than fabricated values.
- The wheel build was not validated because isolated pip build dependencies require network access, which is unavailable in this environment.
