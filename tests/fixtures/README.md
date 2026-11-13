# Official aggregate fixture

`september-2026.ods` is a reduced, aggregate-only copy of the official
[September 2026 ODS](https://repositorio.dados.gov.br/segrt/cargos%20vagos%20e%20vacancia/2026/CargosVagosVacancias_202609.ods),
retrieved 2026-11-13. Original SHA-256:
`545aa858ae68dd60e5ef7463f548ce3ff3fb5cfdfa5d71978348f5436b1aae89`.

Both sheet headers, PF rows and other-organization perito rows were retained;
other rows were removed. Retained cell values/attributes are unchanged, including
normal numeric cells and large trailing repeated empty cells. XML namespace
prefixes and ZIP packaging were regenerated. No individual personnel data is
present. The PF classes sum to 1,195 approved, 1,108 occupied and 87 vacant.

`tests.sources` supplies controlled archive/year listings, ODS bytes and a UTC
clock to the complete refresh/build interface. Variants of these source bytes
are deliberate test scenarios, not additional official observations.
