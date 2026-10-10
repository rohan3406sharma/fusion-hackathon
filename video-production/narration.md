# Narration script

Final voiceover as rendered: 673 words, 247.5 s of speech in a 4:53.05 video (138 words per minute overall). Voice: Kokoro-82M `af_heart`, speed 0.92, generated locally.
Times are the exact start/end of each synthesised line in the final mix. Edit `scripts/narration.json`, then rerun the pipeline (see README).
Numbers are spelled out for the voice; the captions file uses digits.

## Act 1 · The hook  (0:00.00–0:19.76)

- `0:01.60` **L01** — Imagine checking every factory you invest in against the climate map.
- `0:06.16` **L02** — Floods. Heat. Drought. Every site comes back clear.
- `0:10.33` **L03** — Now ask a harder question.
- `0:12.49` **L04** — What if the climate event that hurts your portfolio most... never touches anything you own?

## Act 2 · The problem  (0:19.76–0:39.29)

- `0:20.16` **L05** — It's not hypothetical.
- `0:21.89` **L06** — In twenty twenty-three, drought drove the lake that feeds the Panama Canal to record lows for the season.
- `0:28.54` **L07** — The canal cut its daily bookings, step by step, down to eighteen ships.
- `0:33.61` **L08** — The hazard wasn't at anyone's factory. It was in a shared link of the chain.

## Act 2 · The problem (evidence)  (0:39.29–1:01.98)

- `0:39.59` **L09** — Research confirms the pattern: when a natural disaster hits a supplier, its customers lose output too, and their market value falls.
- `0:48.69` **L10** — After Japan's twenty eleven earthquake, the disruption travelled further: to suppliers' suppliers, and customers' customers.
- `0:57.13` **L11** — A screen that only checks your own sites... sees none of it.

## Act 3 · The core idea  (1:01.98–1:44.34)

- `1:02.58` **L12** — This is the Fin zero four Climate Exposure Graph.
- `1:06.20` **L13** — It maps a food supply chain as a network, and lets a climate shock travel through it, hop by hop.
- `1:12.88` **L14** — Then it flips the usual question.
- `1:15.01` **L15** — Not, what if this event hits? But: which events would hurt most, and how much of that would a site check miss?
- `1:22.16` **L16** — Bank supervisors call this a reverse stress test: start from the damage, then search for its causes.
- `1:29.31` **L17** — One honest note: real supplier links are rarely published, so this network is synthetic. A hundred and two companies, eighteen holdings.
- `1:38.34` **L18** — The one real dataset is the E U's river-flood map, used as context.

## Act 4 · Live demo: search  (1:44.34–2:05.92)

- `1:44.94` **L19** — Here it is, running.
- `1:46.49` **L20** — Open the Hidden Exposure Finder, and search.
- `1:50.76` **L21** — Seven hundred and eighty synthetic events, scored against the portfolio in under a second.
- `1:56.78` **L22** — A hundred and sixty-five distinct events are hidden-only: no holding is hit directly, yet the portfolio still loses value.

## Act 4 · Live demo: the top event  (2:05.92–2:36.00)

- `2:06.11` **L23** — The worst: a drought at a Dutch power-grid operator the portfolio doesn't own.
- `2:11.45` **L24** — A location-only screen scores it at zero. The network model: one point one three percent of the portfolio's annual value added.
- `2:20.60` **L25** — And it holds up: across two hundred uncertainty draws, it stays in the top five every time. Rankings that don't are flagged as fragile.
- `2:29.72` **L26** — A matrix shows who can hurt whom: upstream nodes that several holdings quietly share.

## Act 4 · Live demo: the path  (2:36.00–2:53.28)

- `2:36.20` **L27** — Open it as a scenario, and the path appears.
- `2:40.53` **L28** — The grid powers a cheese and yogurt maker, which loses about a quarter of its output. That shortfall flows on to a grocery chain.
- `2:49.05` **L29** — Three holdings are hit. None of them directly.

## Act 4 · Live demo: protect  (2:53.28–3:12.51)

- `2:53.47` **L30** — So, can you protect against it?
- `2:56.33` **L31** — Give the optimiser three million dollars a year. It picks five interventions that cut the average impact of the ten worst events by about five percent.
- `3:06.44` **L32** — A brute-force check of a hundred and ninety-seven plans finds nothing better.

## Act 5 · How it works  (3:12.51–3:54.38)

- `3:13.11` **L33** — Under the hood, it's deliberately simple: one Python service, one React app, one database file.
- `3:19.90` **L34** — Each event's direct hit combines three separate inputs: hazard, exposure, and vulnerability.
- `3:26.52` **L35** — Then a vectorised engine pushes it along every supply link. Each link passes on only part of the shock, depending on dependency, substitutes and stock on hand, so shocks shrink with every hop.
- `3:39.84` **L36** — The same engine powers the finder, every scenario, the uncertainty draws, and the optimiser.
- `3:46.34` **L37** — Even the AI copilot is boxed in: it can explain the results, but it's never allowed to calculate them.

## Act 6 · Impact and limits  (3:54.38–4:29.20)

- `3:54.78` **L38** — So what does this change?
- `3:56.58` **L39** — A typical climate dashboard tests the scenario you chose. This one searches for the ones you didn't think of, and shows how much a site check can't see.
- `4:06.25` **L40** — For a risk team, that's a starting list: which grids, ports and suppliers to check first.
- `4:12.22` **L41** — And it's honest about its limits: synthetic data, an uncalibrated, unvalidated model, and no event probabilities. It ranks consequence, not likelihood.
- `4:23.07` **L42** — The next step is real supplier data, and real losses to test against.

## Act 7 · The payoff  (4:29.20–4:53.05)

- `4:29.80` **L43** — So, back to that clean climate map.
- `4:32.33` **L44** — In this model, the biggest hidden threat wasn't at any factory the portfolio owns. It was a drought at a power grid.
- `4:40.33` **L45** — Climate risk doesn't stop at the factory fence.
- `4:43.94` **L46** — The Fin zero four Climate Exposure Graph. Find the exposure your site checks can't see.
