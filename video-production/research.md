# Research log

Every external fact in the video, where it came from, when it was checked, and where it appears.
Checked on 9–10 October 2026. Project-internal numbers (from the running app) are listed separately at
the end; they are synthetic-data model outputs, not research findings.

## External claims used on screen or in the narration

| # | Claim as used in the video | Source (primary where possible) | Date | Scene |
|---|---|---|---|---|
| 1 | In 2023 drought drove Gatún Lake, which feeds the Panama Canal's locks, to "unprecedented levels for this time of year"; October 2023 rainfall was the lowest since 1950 (41% below). | Panama Canal Authority (ACP), *Advisory to Shipping No. A-48-2023*, "Reduction in Transits Due to the Ongoing Deficit in Precipitation in the Canal Watershed" (read from the PDF text; copy hosted at https://hksoa.org/wp-content/uploads/2023/12/CAN2318-Annex-B-ACP-Advisory-to-Shipping-A-48-2023.pdf). Corroborated by Reuters via gCaptain, https://gcaptain.com/panama-canal-reduces-daily-transits/ | 30 Oct 2023 | s02 (0:20–0:39) |
| 2 | Daily booking slots were cut step by step: 25 (from 3 Nov), 24 (7 Nov), 22 (Dec), 20 (Jan 2024), then 18 per day from 1 Feb 2024. | Same ACP advisory A-48-2023. Capacity had already been cut to about 32 vessels a day since 30 Jul 2023 (same advisory; not shown as a bar to avoid mixing units). | 30 Oct 2023 | s02 |
| 3 | When a natural disaster hits a supplier, its customers lose output too, and their market value falls (especially when inputs are specific). | Barrot, J.-N. & Sauvagnat, J. (2016), "Input Specificity and the Propagation of Idiosyncratic Shocks in Production Networks", *Quarterly Journal of Economics* 131(3), 1543–1592. Abstract via RePEc/IDEAS: https://ideas.repec.org/a/oup/qjecon/v131y2016i3p1543-1592..html | 2016 | s03 (0:39–0:48) |
| 4 | After the 2011 Great East Japan Earthquake the disruption propagated upstream and downstream along supply chains, to direct and indirect suppliers and customers. | Carvalho, V. M., Nirei, M., Saito, Y. U. & Tahbaz-Salehi, A. (2021), "Supply Chain Disruptions: Evidence from the Great East Japan Earthquake", *Quarterly Journal of Economics* 136(2), 1255–1321, doi:10.1093/qje/qjaa044. Abstract via https://atiro.turing.ac.uk/esploro/outputs/journalArticle/Supply-chain-disruptions-Evidence-from-the/9921250809548 | 2021 | s03 (0:48–0:57) |
| 5 | Bank supervisors call this a *reverse stress test*: "…starts from the identification of the pre-defined outcome … and then explores scenarios and circumstances that might cause this to occur." | European Banking Authority, *Final Report: Guidelines on institutions' stress testing*, EBA/GL/2018/04, definition (10) (read from the PDF; copy hosted by the Bank of England: https://www.bankofengland.co.uk/-/media/boe/files/paper/2020/december/gl-institutions-stress-testing.pdf) | 19 Jul 2018 | s04 (1:22–1:29) |
| 6 | Supplier links are rarely published: US rules require a company to report revenue from any single external customer of 10% or more of revenue, but it need not name the customer. | FASB ASC 280-10-50-42, as summarised by Deloitte DART Roadmap, "5.7 Information About Major Customers": https://dart.deloitte.com/USDART/home/codification/presentation/asc280-10/roadmap-segment-reporting/chapter-5-entity-wide-disclosures/5-7-information-about-major-customers | current | s04 footnote (1:29–1:38) |
| 7 | The one real dataset: JRC / Copernicus global river-flood hazard maps, 100-year return period, CC BY 4.0. | Dataset record: JRC Global River Flood Hazard Maps v2.1 (Baugh, Colonese, D'Angelo, Dottori, Neal, Prudhomme, Salamon, 2024), e.g. https://developers.google.com/earth-engine/datasets/catalog/JRC_CEMS_GLOFAS_FloodHazard_v2_1 . The project's own citation and retrieval notes are in `docs/DATA_SOURCES.md` and `backend/data/hazard_layers/jrc_flood_rp100.json`. | 2024 (retrieved by the project 9 Oct 2026) | s04 (1:38–1:43), s11 credits |

### How the external facts are worded (limits respected)
- The canal example is presented as an illustration of a hazard at a *shared link*, not as a quantified loss for any company.
- Claims 3 and 4 are stated at the level of the abstracts (direction of effect, reach to indirect partners). No magnitudes from those papers are quoted, because only abstracts were checked.
- The project's evidence review (`read this before building/Evidence synthesis_fs4.docx`) found no study comparing network-aware and location-only exposure on the same portfolio. The video does not claim the app's comparison is validated.

## Project numbers shown in the video (from the running app, not research)
All read from the live API/UI on 9 Oct 2026 (isolated instance, fresh database, default data, seed 42, 200 draws) and cross-checked against `captures/manifest.json` (the text of every annotated element). They are model outputs on **synthetic** data: not calibrated, not validated, not forecasts.

| Value | Where in the app | Scene |
|---|---|---|
| 102 entities, 240 relationships, 18 holdings, 0 observed | Data & methodology KPIs; `docs/DATA_DICTIONARY.md` | s04 |
| 780 events evaluated, 268 distinct, 165 hidden-only | Hidden exposure finder KPIs | s05 |
| Runtime 0.69 s (this capture; 0.41–0.69 s across runs) | Finder KPI "Runtime" | s05 (narrated as "under a second") |
| Drought at Dutch Regional Grid Operator: portfolio impact 1.13%, location-only 0.00%, hidden share 100%, 3 holdings, P(top 5) 100% | Finder hidden-only table, row 1 | s06, s10, s11 |
| Rows 4–5 fragile: 39%, 38% | Finder table | s06 |
| Top single point of failure: Rotterdam Terminal Operator → Hamburg Coffee Roasters 24%, Antwerp Chocolatier 21% | Finder "Single points of failure" | s06 |
| Path: grid → Utrecht Cheese and Yogurt Maker (25.7%) → Rhineland Grocery Group (6.7%); grid directly disrupted 30.2% | Scenario results paths; graph detail panel; comparison table | s07, s09 |
| Direct disruption 0.0% for Utrecht, Rhineland, Manchester; portfolio 0.00% → 1.13% | Scenario results "Location-only vs network-aware" | s07 |
| Optimiser, $3M/yr: plan $2.46M, 5 interventions, tail 3.25% → 3.09% (5.0% lower), gap 0.0% over 197 plans, positive in 100% (50/50) of draws | Finder "Protect against these events" | s08 |
| Copilot: "Language-model phrasing, validated (qwen3:8b)" with provenance chips | Finder copilot panel | s09 |
| Rotterdam terminal flood reaches 7 holdings; Daloa 350 km drought 0.87% | Finder results | s10 |
| Hook cascade: Daloa Cocoa → San-Pedro Cocoa Grinding → Antwerp Chocolatier → Rhineland Grocery; San-Pedro → Ludhiana Biscuits | Real links in `backend/data/fnb_relations.json` (synthetic dataset); holdings flashed are the three this event reaches in the finder | s01 |
