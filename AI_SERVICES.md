# AI grading services

The default grader is **LexAI 3.0**, powered by Cencori's `gpt-6-luna` model.
The model ID and Cencori project key stay on the server. Scoring responses show
`model_used: "LexAI 3.0"` and `scoring_method: "lexai"`.

## Configure Cencori

Create a project key in the [Cencori console](https://console.cencori.com/home),
then set these environment variables on the backend:

```bash
CENCORI_API_KEY=csk_...
CENCORI_MODEL=gpt-6-luna
```

`CENCORI_BASE_URL` defaults to `https://api.cencori.com/v1`. Keep the key on the
server; never send it from a browser or commit it to Git. Cencori accepts chat
completions at `/v1/chat/completions` using Bearer authentication.

## Fallbacks

If Cencori cannot grade, the manager tries configured PaLM, Cohere and Hugging Face
services in that order. Set `PALM_API_KEY`, `COHERE_API_KEY`, or
`HUGGINGFACE_API_KEY` only if you want those fallbacks. If all providers fail,
`ALLOW_SIMILARITY_FALLBACK=1` permits a text similarity estimate that always needs
lecturer review. Set it to `0` to return a 503 instead.

The public `/api/v1/health` response lists the Cencori grader as `lexai` with
model `LexAI 3.0`. Its `connected` flag means a key is configured; the first
grading request confirms whether the key and model work.
