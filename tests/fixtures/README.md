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

## June 2025-inclusive national history

`national/` contains 14 additional reduced official ODS files, downloaded and
independently checked on 2026-11-14 UTC; September reuses the fixture above.
Original filenames (including lowercase variants) are unchanged. Each retains
both sheet headers, the PF organization aggregate, all four PF PCF class rows,
one other PF career and one other-organization perito row. Cell values and
attributes are unchanged; only rows, namespace prefixes and ZIP packaging were
reduced/regenerated. These aggregate-only fixtures total about 27 KB.

Original resources are under
`https://repositorio.dados.gov.br/segrt/cargos%20vagos%20e%20vacancia/YYYY/`:

| Original filename | Original SHA-256 |
| --- | --- |
| `CargosVagosVacancias_202506.ods` | `c8dc2d8375b17a3963f4937e3588572a5ed5da27cf816b8b39bc55e54dd93035` |
| `cargosvagosvacancias_202508.ods` | `ae2160baf26ca53743355bcf955a00b106800af243ad13d0be1024a4e99063d4` |
| `cargosvagosvacancias_202509.ods` | `87514503b072ee4ec494250f24313e593fe4176915ce259a7409ed97ad8347ab` |
| `cargosvagosvacancias_202510.ods` | `a228708ca3d45b2ae8245c4925d8dbca944d8ba1c9bc7e517aa0c857f7e7837d` |
| `CargosVagosVacancias_202511.ods` | `25b88fa0c19f645ee656d4a78702a527dd749ec042e49de30945a91f1f3351e2` |
| `cargosvagosvacancias_202512.ods` | `5b31bdf991aa730d67c9f5cbd12ea208bfa45bf862bfd2dd3906a0ea4cfd882a` |
| `CargosVagosVacancias_202601.ods` | `1013e58a40c5ac9e39cb749ad811900058e6ef7e0421f12ee6f15e2ffcf8248c` |
| `CargosVagosVacancias_202602.ods` | `768b4db2324215266c793749e4b138831fa0196d61dc34d828019950b3c3cd2b` |
| `CargosVagosVacancias_202603.ods` | `d5b444a57d0e47347f40b990c245d6e5a8d3d6710bb4df74008322112fc581e1` |
| `CargosVagosVacancias_202604.ods` | `9856df7d2c19e506887b113fb7989d0dbad7c968a48f33aa28f2b58cf5684990` |
| `CargosVagosVacancias_202605.ods` | `bd8df5eb4eb059c6f3b836d31a01455d3c1b703b13e38253b8ffea2dd4c6a145` |
| `CargosVagosVacancias_202606.ods` | `7742913d4a7a8de6f20c9f6898ff5b908acff4d4cab773ae8713507e4bb06abd` |
| `CargosVagosVacancias_202607.ods` | `ca4527d13ed18e262f623a080bdf3389ef13350ae3a3432b7ddaa0b2309fa446` |
| `CargosVagosVacancias_202608.ods` | `b7dccdbc6db7875ed65da5343f96dda8a1c1ecce55d16039c50ddf4179830222` |

July 2025 was unavailable and has no fixture. The literal 15-month expected
series in `tests/test_dashboard.py` comes from independent source research, not
the importer. Class allocations are retained per month, notably May/June 2026:
the same 1,083 occupied / 112 vacant national total spans a class redistribution,
not evidence of personnel flows. Equal approved/distributed totals in these
sources are observations, not a required invariant or production constant.

`tests.sources` supplies controlled archive/year listings, ODS bytes and a UTC
clock to the complete refresh/build interface. Variants of these source bytes
are deliberate test scenarios, not additional official observations.
