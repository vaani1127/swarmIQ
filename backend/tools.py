from dotenv import load_dotenv
from groq import Groq
from tavily import TavilyClient
import os

load_dotenv()


def llm(system, user, json_mode=False):
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    kwargs = {
        "model": "llama-3.3-70b-versatile",
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
