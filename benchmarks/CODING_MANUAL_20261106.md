# Coding manual: blinded document-level finding labels

This manual is the only coding guidance for the pilot. Do not consult the
auditor, its reports, the frozen benchmark, or the other reviewer's worksheet.
If any other document describes automated results, do not read it.

## Materials

- `papers/<PMCID>.md`: the supplied manuscript text. Judge only this text.
- `reviewer_N.json`: your worksheet. Each case names one paper (`pmcid`) and
  one finding code (`code`).

## Task

For every case, replace `"verdict": null` with JSON `true` or JSON `false`.
Do not leave blanks, strings, numbers or missing cases. You may add a `notes`
field, but the study uses only the boolean.

`true` means the finding code is correct for the supplied text under the
definition below. `false` means it is not correct. Judge each case
independently; the codes are not exclusive, so several can be true for one
paper.

Use only the supplied text. Do not search external literature, publisher
pages or supplementary material. Support is judged against evidence reported
inside the supplied text.

## `potential_overclaim` (primary)

**Definition.** The document contains at least one statement that asserts a
stronger scientific conclusion than the evidence reported in the supplied
text supports.

Answer `true` if at least one statement:

- claims proof, guarantee, certainty or universality about a biological,
  clinical, physical or social phenomenon ("proves", "guarantees", "always",
  "never", "undeniably", or equivalent), and the supplied evidence does not
  justify that strength; or
- asserts causation from a design that only reports association, without
  adequate qualification; or
- generalises a clinical or biological benefit beyond the studied population,
  intervention or setting without support in the text.

Answer `false` if no such statement exists, or if every candidate is one of:

- an absolute word used non-claimingly, such as a procedural statement
  ("samples were always stored at 4 °C");
- negated, hedged or explicitly limited ("we do not prove", "may", "in this
  sample");
- a quotation or a description of another author's claim;
- a definition, mathematical condition or methodological constraint; or
- directly supported by the design and results reported in the text.

One justified overclaiming statement is enough for `true`. Do not count
occurrences and do not judge grammar or writing style.

## `references_section_missing` (secondary)

**Definition.** The supplied text contains recognizable in-text citations but
no references section with at least one recognizable reference entry.

Answer `true` if both hold:

- at least one recognizable citation marker appears in the body (bracketed
  numeric citation, or an author-year citation such as "Smith, 2020" or
  "Smith (2020)"); and
- no section headed References, Bibliography or Literature Cited contains at
  least one reference entry.

Answer `false` otherwise, including papers with no citation markers and
papers whose supplied text includes a references section with entries.

**Known limitation.** The supplied text is a BioC-derived rendering that can
omit a published reference list. A `true` verdict may therefore reflect the
supplied rendering rather than a deficiency in the published article. Apply
the definition to the supplied text, not to the publisher's website.

## Independence and declarations

Work alone. Do not discuss cases, verdicts or the tool with the other
reviewer before both worksheets are submitted. Do not run the auditor on
these texts. Return the completed worksheet together with a signed
declaration of qualifications and conflicts to the study organizer. Your
reviewer ID in the worksheet is a pseudonym; the declaration is kept outside
the repository.

Software can check completeness and hashes. It cannot verify that you are
qualified, independent or actually blinded, so these instructions depend on
your honest compliance.
