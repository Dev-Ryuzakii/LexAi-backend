# CBT integration examples

These examples call LexAI from a **CBT backend**. Keep `LEXAI_API_KEY` on the
server. It is a LexAI account API key, separate from the `CENCORI_API_KEY` in
the LexAI backend.

- [`javascript_api_example.js`](javascript_api_example.js): use the local
  JavaScript SDK (`sdk/javascript`) from a Node.js backend.
- [`cbt_server_example.ts`](cbt_server_example.ts): a typed function for a CBT
  server that keeps provisional scores out of final totals.
- [`python_api_example.py`](python_api_example.py): call the REST API using
  `requests` from a Python backend.

Both examples expect the CBT server to authenticate the student and load the
question and marking guide from its own database. They use `/api/v1/score`, so
LexAI does not store the student's response. A `needs_review` grade stays
provisional; a `503 SCORE_001` becomes `pending`, never zero.

See the [integration guide](../API_INTEGRATION_GUIDE.md) for API key creation,
the alternative stored-assessment flow, and error handling.
