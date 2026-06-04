import os

from dotenv import load_dotenv
from openai import OpenAI
from tavily import TavilyClient

load_dotenv()

# Provider-agnostic LLM config. Defaults point at GitHub Models (free, OpenAI-compatible,
# Microsoft-hosted). Override LLM_BASE_URL/LLM_API_KEY/LLM_MODEL to switch to Azure OpenAI,
# OpenAI direct, or any other OpenAI-compatible endpoint without code changes.
_LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://models.github.ai/inference")
_LLM_API_KEY = os.getenv("LLM_API_KEY") or os.getenv("GITHUB_TOKEN")
_LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-4o-mini")


def llm(system, user, json_mode=False):
    try:
        client = OpenAI(base_url=_LLM_BASE_URL, api_key=_LLM_API_KEY)
        kwargs = {
            "model": _LLM_MODEL,
            "max_tokens": 2048,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        response = client.chat.completions.create(**kwargs)
        return response.choices[0].message.content
    except Exception as e:
        msg = str(e).lower()
        if (
            "connection" in msg
            or "unreachable" in msg
            or "failed to establish" in msg
            or "name or service not known" in msg
            or isinstance(e, (ConnectionError, TimeoutError, OSError))
        ):
            raise RuntimeError(
                f"LLM endpoint unreachable at {_LLM_BASE_URL} — "
                "check LLM_BASE_URL / LLM_API_KEY in .env"
            ) from e
        raise


def web_search(query, n=3):
    try:
        client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
        results = client.search(query, max_results=n)
        output = ""
        for r in results.get("results", []):
            url = r.get("url", "")
            content = r.get("content", "")[:400]
            output += f"[{url}]\n{content}\n\n"
        return output
    except Exception as e:
        return f"Search failed: {e}"


if __name__ == "__main__":
    print(web_search("Zepto India startup"))
    print(llm("You are helpful.", "Say hello in one word."))
