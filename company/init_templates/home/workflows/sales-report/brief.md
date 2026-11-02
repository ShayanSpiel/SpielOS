# Sales report example

Status: draft example. No real company baseline, brand approval or business result is implied.

A finance lead supplies a title and a bounded list of sales amounts in one agreed
currency. Return the unchanged title, exact sum and row count. Do not infer
missing rows, combine currencies, send reports or claim business impact. This
example accepts nonnegative totals; the refund counterexample must fail quality.

The local script takes one JSON object on standard input and returns one JSON
object on standard output. The evaluation harness checks each accounting rule
independently for example cases and previously unseen production inputs.

Run representative, held-out and negative inputs as actual candidate runs, then
have an independent reviewer inspect their evaluated results before release.
The expected example in examples/ is a reference, never release evidence by itself.
