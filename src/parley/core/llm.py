from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass

import requests

from .config import Settings


class LLMError(RuntimeError):
    pass


@dataclass
class BackendProbe:
    online: bool
    message: str
    models: list[str]


def normalize_base_url(backend: str, base_url: str) -> str:
    url = (base_url or "").strip().rstrip("/")
    if backend == "llamacpp":
        if not url:
            url = "http://127.0.0.1:8080/v1"
        url = url.removesuffix("/chat/completions")
        if not url.endswith("/v1"):
            url = f"{url}/v1"
    return url


def _request_error(backend: str, url: str, exc: requests.RequestException) -> LLMError:
    if isinstance(exc, requests.Timeout):
        return LLMError(
            f"Timed out while contacting {backend} at {url}. "
            "The model may be busy or the reply took too long."
        )
    if isinstance(exc, requests.ConnectionError):
        return LLMError(
            f"Could not connect to the {backend} backend at {url}. "
            "Check that the server is running and the URL is correct."
        )
    return LLMError(f"Communication with {backend} at {url} failed: {exc}")


def _response_error(backend: str, response: requests.Response) -> LLMError:
    detail = ""
    try:
        response.encoding = "utf-8"
        payload = response.json()
        if isinstance(payload, dict):
            detail = str(
                payload.get("error")
                or payload.get("message")
                or payload.get("detail")
                or ""
            )
    except ValueError:
        detail = response.text[:500]
    if response.status_code == 404:
        return LLMError(
            f"{backend} returned 404. Check that the selected model exists "
            f"and that the URL is correct. Detail: {detail or 'not provided'}"
        )
    return LLMError(
        f"{backend} returned HTTP {response.status_code}. "
        f"Detail: {detail or 'not provided'}"
    )


def _ollama_payload(
    settings: Settings, model: str, messages: list[dict], stream: bool
) -> dict:
    return {
        "model": model,
        "messages": messages,
        "stream": stream,
        "keep_alive": settings.keep_alive,
        "options": {
            "num_ctx": settings.num_ctx,
            "num_predict": settings.num_predict,
            "temperature": settings.temperature,
            "top_p": settings.top_p,
        },
    }


def _llamacpp_payload(
    settings: Settings,
    model: str,
    messages: list[dict],
    stream: bool,
) -> dict:
    return {
        "model": model or "local-model",
        "messages": messages,
        "stream": stream,
        "temperature": settings.temperature,
        "top_p": settings.top_p,
        "max_tokens": settings.num_predict,
    }


def list_models(settings: Settings, backend: str, base_url: str) -> list[str]:
    base = normalize_base_url(backend, base_url)
    timeout = (settings.connect_timeout, 15)
    try:
        if backend == "ollama":
            response = requests.get(f"{base}/api/tags", timeout=timeout)
            response.raise_for_status()
            payload = response.json()
            models = payload.get("models", []) if isinstance(payload, dict) else []
            return sorted(
                str(item.get("name", ""))
                for item in models
                if isinstance(item, dict) and item.get("name")
            )
        if backend == "llamacpp":
            response = requests.get(f"{base}/models", timeout=timeout)
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, dict):
                items = payload.get("data", [])
            elif isinstance(payload, list):
                items = payload
            else:
                items = []
            return sorted(
                str(item.get("id", ""))
                for item in items
                if isinstance(item, dict) and item.get("id")
            )
        raise LLMError(f"Unknown backend: {backend}")
    except requests.RequestException as exc:
        raise _request_error(backend, base, exc) from exc


def probe_backend(settings: Settings, backend: str, base_url: str) -> BackendProbe:
    base = normalize_base_url(backend, base_url)
    try:
        models = list_models(settings, backend, base)
    except LLMError as exc:
        return BackendProbe(False, str(exc), [])
    if not models:
        return BackendProbe(
            True,
            f"{backend} is online at {base}, but no model was listed.",
            [],
        )
    preview = ", ".join(models[:5])
    if len(models) > 5:
        preview += f" (+{len(models) - 5})"
    return BackendProbe(True, f"{backend} is online at {base}. Models: {preview}", models)


def stream_chat(
    settings: Settings,
    backend: str,
    base_url: str,
    model: str,
    messages: list[dict],
) -> Iterator[str]:
    base = normalize_base_url(backend, base_url)
    timeout = (settings.connect_timeout, settings.read_timeout)

    if backend == "ollama":
        url = f"{base}/api/chat"
        payload = _ollama_payload(settings, model, messages, True)
        try:
            with requests.post(
                url, json=payload, stream=True, timeout=timeout
            ) as response:
                if response.status_code >= 400:
                    raise _response_error("Ollama", response)
                # requests assumes ISO-8859-1 for many text responses. The
                # local model servers send UTF-8, so decode explicitly.
                response.encoding = "utf-8"
                for line in response.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(data, dict):
                        continue
                    if data.get("error"):
                        raise LLMError(f"Ollama: {data['error']}")
                    content = (data.get("message") or {}).get("content")
                    if content:
                        yield content
                    if data.get("done"):
                        break
        except requests.RequestException as exc:
            raise _request_error("Ollama", url, exc) from exc
        return

    if backend == "llamacpp":
        url = f"{base}/chat/completions"
        payload = _llamacpp_payload(settings, model, messages, True)
        try:
            with requests.post(
                url,
                json=payload,
                stream=True,
                timeout=timeout,
                headers={"Accept": "text/event-stream"},
            ) as response:
                if response.status_code >= 400:
                    raise _response_error("llama.cpp", response)
                response.encoding = "utf-8"
                content_type = response.headers.get("Content-Type", "")
                if (
                    "application/json" in content_type
                    and "event-stream" not in content_type
                ):
                    data = response.json()
                    choices = data.get("choices") or []
                    if choices and isinstance(choices[0], dict):
                        message = choices[0].get("message") or {}
                        content = message.get("content")
                        if content:
                            yield content
                    return
                for line in response.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    if line.startswith("data:"):
                        line = line[5:].strip()
                    if line == "[DONE]":
                        break
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(data, dict):
                        continue
                    if data.get("error"):
                        error = data["error"]
                        if isinstance(error, dict):
                            error = error.get("message", error)
                        raise LLMError(f"llama.cpp: {error}")
                    choices = data.get("choices") or []
                    if not choices or not isinstance(choices[0], dict):
                        continue
                    choice = choices[0]
                    delta = choice.get("delta") or {}
                    if not isinstance(delta, dict):
                        delta = {}
                    content = delta.get("content")
                    if not content:
                        message = choice.get("message") or {}
                        content = (
                            message.get("content")
                            if isinstance(message, dict)
                            else None
                        )
                    if content:
                        yield content
        except requests.RequestException as exc:
            raise _request_error("llama.cpp", url, exc) from exc
        return

    raise LLMError(f"Unknown backend: {backend}")


def complete_chat(
    settings: Settings,
    backend: str,
    base_url: str,
    model: str,
    messages: list[dict],
) -> str:
    return "".join(stream_chat(settings, backend, base_url, model, messages)).strip()


def unload_ollama(settings: Settings, base_url: str, model: str) -> str:
    base = normalize_base_url("ollama", base_url)
    try:
        response = requests.post(
            f"{base}/api/generate",
            json={"model": model, "keep_alive": 0, "prompt": ""},
            timeout=(settings.connect_timeout, 15),
        )
        response.raise_for_status()
        return "Pedido de descarga enviado ao Ollama."
    except requests.RequestException as exc:
        raise _request_error("Ollama", base, exc) from exc
