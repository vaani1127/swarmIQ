import os

from dotenv import load_dotenv
from openai import AzureOpenAI
from tavily import TavilyClient

load_dotenv()


def llm(system, user, json_mode=False):
    try:
        client = AzureOpenAI(
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
        )
        kwargs = {
            "model": os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),
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
        if "connection" in str(e).lower() or "unreachable" in str(e).lower() or "failed to establish" in str(e).lower() or "name or service not known" in str(e).lower() or isinstance(e, (ConnectionError, TimeoutError, OSError)):
            raise RuntimeError("Azure OpenAI endpoint unreachable — check AZURE_OPENAI_ENDPOINT in .env") from e
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
