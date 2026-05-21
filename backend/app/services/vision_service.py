"""Vision caption generation — OpenAI-compatible API (v2.0)"""

import requests
from app.config import config
from app.services.image_loader import get_image_base64, get_image_mime_type


def generate_caption(
    image_path: str,
    model: str | None = None,
    provider: str | None = None,
    context_text: str = "",
) -> str:
    """Generate a caption for an image using a Vision LLM."""
    provider = provider or "openai"
    if provider != "openai":
        raise ValueError(f"Vision captioning only supports openai-compatible API, got: {provider}")

    model = model or config.VISION_MODEL
    image_b64 = get_image_base64(image_path)
    mime_type = get_image_mime_type(image_path)

    system_prompt = (
        "你是一个文档图像分析助手。请用中文描述这张图片的内容、图表信息、关键数据，"
        "使读者能够在不看图的情况下理解其含义。描述控制在2-4句话。"
    )
    if context_text:
        system_prompt += f"\n\n图片所在页面的文本内容供参考:\n{context_text[:500]}"

    return _call_vision_api(model, image_b64, mime_type, system_prompt)


def _call_vision_api(model: str, image_b64: str, mime_type: str, prompt: str) -> str:
    if not config.VISION_API_BASE:
        raise RuntimeError("VISION_API_BASE not configured")
    base_url = config.VISION_API_BASE.rstrip("/")
    if not config.VISION_API_KEY:
        raise RuntimeError("VISION_API_KEY not configured (fallback: CHAT_API_KEY)")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {config.VISION_API_KEY}",
    }
    payload = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{image_b64}"},
                },
            ],
        }],
        "max_tokens": 300,
    }
    resp = requests.post(
        f"{base_url}/chat/completions", headers=headers, json=payload, timeout=120
    )
    try:
        resp.raise_for_status()
    except requests.HTTPError as e:
        raise RuntimeError(f"Vision API failed: {resp.text}") from e
    return resp.json()["choices"][0]["message"]["content"]
