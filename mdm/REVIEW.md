# Review rules for the labelled pairs

`mdm/labelled_pairs.csv` holds about 300 candidate pairs (SEC filer, GLEIF record) drawn across
the match-probability bands by `python -m mdm.cli sample`. Each pair gets `is_match` 1 or 0 by
the rules below, written down before the first pair was looked at, so the labels do not bend
towards the model's score. The reviewer does not look at `match_probability` while deciding.

## A pair is a match (1) when

1. The names denote the same legal entity once legal-form words (Inc, Corp, Ltd, LLC, plc,
   N.V., S.A., Holdings only where both carry it) and punctuation are ignored, **and**
2. nothing in the address contradicts it: same country, and the city agrees or is a known
   move (the GLEIF record shows the registered seat, the SEC record the business address; a
   Delaware seat against a business city elsewhere is not a contradiction), **or**
3. a ticker of the SEC filer appears among the GLEIF record's other names (strong evidence on its
   own, unless the names contradict it).

## A pair is not a match (0) when

* the names differ in a distinguishing word (e.g. "Capital" vs "Bancorp", a different place
  name, "Trust I" vs "Trust II", a fund series), **or**
* one is the parent and the other a subsidiary, a fund, a trust or an SPV of it: the golden
  record is the legal entity, not the group, **or**
* the countries differ, or the cities differ with no sign of a move and the names are generic.

## When the rows are not enough

Where name and address leave it open, the reviewer marks `is_match` empty and writes the reason
in `note`. Such pairs are left out of precision and recall rather than guessed; their count is
reported next to the metrics.

## Who checked

`checked_by` names the reviewer. Pairs labelled by Claude carry `claude` and the rule number in
`note`; a person who disagrees changes the label and their name, and `python -m mdm.cli score`
recomputes the metrics. Labels are never derived from the model's own score.
