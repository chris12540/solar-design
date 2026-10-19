# Parcel classification

Importer v3 preserves the assessor's `PropertyType` and `PUC` fields as source text and adds nullable `residential`:

| `PropertyType` after trim/case-fold | `residential` |
|---|---|
| `RESIDENTIAL` | `true` |
| `COMMERCIAL`, `VACANT`, `AG` | `false` |
| Blank or any other label | `null` |

`PUC` is retained verbatim, including leading zeroes. It is not used as a fallback classifier. The source contains 1,759,895 structurally valid rows and two malformed rows. The observed labels are `RESIDENTIAL` (1,475,249), `COMMERCIAL` (183,424), `VACANT` (93,951), and `AG` (7,271); no blank `PropertyType` or `PUC` appeared among structurally valid rows. The files' snapshot date is unknown. These counts describe the local source snapshot, not a live county guarantee. Other or future `PropertyType` labels remain unknown until documented.

The profile found 885 distinct PUC values across the source. PUC spans many use codes, so this implementation does not infer residential status from code prefixes or selected codes. The source enum is descriptive evidence, not a complete published mapping specification; its four observed labels have not been independently validated against current assessor policy.

Streaming profile samples for GIS smoke checks (counts are residential rows; APNs are source `FolioKey` values):

| MCR key | Exact recorded name | Residential rows | Example APN | Note |
|---|---|---:|---|---|
| `21648` | CASA ENCANTADORA | 5 | `17704749` | Small group |
| `16920` | PALO VIENTO 1 | 105 | `17707106` | Medium group |
| `17824` | PASEO VILLAGE 2ND REPLAT | 70 | `17704518` | Replat |
| `8150` | GILA BEND ESTATES | 88 | `40361130` | Known missing exact subdivision boundary case |

MCR `62144` includes multiple residential records for the same situs and unit: `16357 E ARROW DR 1-209`, APNs `17627157` and `17627121`. Treat these as separate parcel records unless county GIS establishes their parcel geometry and relationship; the source alone does not prove separate physical units. No owner or mailing fields are included in this profile.
