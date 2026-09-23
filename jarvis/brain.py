# Copyright (c) 2026 Tiago Pereira. All rights reserved.
"""The brain: turns user input into replies, calling skills as needed.

Two modes:
- With an API key, it talks to an OpenAI-compatible chat model and lets the
  model decide when to call skills (tool calling).
- Without a key, it falls back to a tiny keyword router so the skills still work
  offline. The offline path is deliberately dumb; it's a courtesy, not a brain.
"""

from __future__ import annotations

from typing import Any, Iterator

from .config import Config
from .persona import SYSTEM_PROMPT
from .skills import SkillRegistry

# How many tool round-trips we allow per user turn before forcing a text reply.
# Prevents a model that keeps calling tools from looping forever.
MAX_TOOL_ROUNDS = 5


class Brain:
    def __init__(self, config: Config, registry: SkillRegistry) -> None:
        self.config = config
        self.registry = registry
        self._client = None

        # Load cross-session memory and fold known facts into the system prompt
        # so the model uses what it knows about the user. The same instance is
        # shared on the registry, so the memory skills mutate what's injected.
        from .memory import Memory

        memory = getattr(registry, "memory", None) or Memory()
        registry.memory = memory
        system_prompt = SYSTEM_PROMPT + memory.as_prompt_block()

        self._history: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt}
        ]
        if config.has_llm:
            self._client = self._make_client()
        # Share the LLM client + model with the registry so skills that need
        # the vision/chat model (e.g. screenshot-and-describe) can reach it.
        # None in offline mode; such skills degrade gracefully.
        registry.llm_client = self._client
        registry.llm_model = self.config.model

    def _make_client(self) -> Any:
        from openai import OpenAI

        kwargs: dict[str, Any] = {"api_key": self.config.api_key}
        if self.config.base_url:
            kwargs["base_url"] = self.config.base_url
        return OpenAI(**kwargs)

    @property
    def online(self) -> bool:
        return self._client is not None

    @property
    def client(self) -> Any | None:
        """The underlying LLM client, or None in offline mode.

        Shared with the voice layer so TTS/STT can reuse one authenticated
        client instead of constructing their own.
        """
        return self._client

    def respond(self, user_input: str) -> str:
        """Return JARVIS's reply to one line of user input."""
        # If a dangerous action is armed, this turn is its yes/no answer — it
        # never reaches the LLM. That keeps the confirmation in our control:
        # the model can arm an action, but only the user's next word resolves
        # it, and only an explicit "yes" runs it.
        gate = self.registry.gate
        if gate.has_pending:
            reply = gate.resolve(user_input)
            # Record the exchange so the LLM has context on the next turn.
            if self._client is not None:
                self._history.append({"role": "user", "content": user_input})
                self._history.append({"role": "assistant", "content": reply})
            return reply

        if self._client is None:
            return self._offline_respond(user_input)
        return self._llm_respond(user_input)

    def respond_stream(self, user_input: str) -> "Iterator[str]":
        """Yield JARVIS's reply in chunks as it's produced.

        Confirmation answers, the offline path, and tool-running rounds resolve
        to a single chunk (there's nothing to stream mid-way). Only the model's
        final text answer is streamed token-by-token, which is where the
        perceived-latency win is. Callers can always just concatenate the
        chunks to get the same string ``respond`` returns.
        """
        gate = self.registry.gate
        if gate.has_pending:
            reply = gate.resolve(user_input)
            if self._client is not None:
                self._history.append({"role": "user", "content": user_input})
                self._history.append({"role": "assistant", "content": reply})
            yield reply
            return

        if self._client is None:
            yield self._offline_respond(user_input)
            return

        yield from self._llm_respond_stream(user_input)

    # -- Online path --------------------------------------------------------

    def _llm_respond(self, user_input: str) -> str:
        self._history.append({"role": "user", "content": user_input})
        tools = self.registry.tool_schemas()

        for _ in range(MAX_TOOL_ROUNDS):
            response = self._client.chat.completions.create(
                model=self.config.model,
                messages=self._history,
                tools=tools or None,
            )
            message = response.choices[0].message

            # Record the assistant turn (content and/or tool calls) verbatim.
            self._history.append(message.model_dump(exclude_none=True))

            if not message.tool_calls:
                return message.content or ""

            # Run each requested skill and feed the results back in.
            for call in message.tool_calls:
                result = self.registry.dispatch(
                    call.function.name, call.function.arguments
                )
                self._history.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": result,
                    }
                )

        # Ran out of tool rounds; ask the model for a plain answer.
        response = self._client.chat.completions.create(
            model=self.config.model,
            messages=self._history,
        )
        content = response.choices[0].message.content or ""
        self._history.append({"role": "assistant", "content": content})
        return content

    def _llm_respond_stream(self, user_input: str) -> Iterator[str]:
        """Like _llm_respond, but streams the final text answer in chunks.

        Tool rounds run non-streamed (we need the whole tool call before we can
        execute it). Once the model produces a plain text answer, we request it
        with stream=True and yield deltas as they arrive.
        """
        self._history.append({"role": "user", "content": user_input})
        tools = self.registry.tool_schemas()

        for _ in range(MAX_TOOL_ROUNDS):
            response = self._client.chat.completions.create(
                model=self.config.model,
                messages=self._history,
                tools=tools or None,
            )
            message = response.choices[0].message
            self._history.append(message.model_dump(exclude_none=True))

            if not message.tool_calls:
                # No tools this round. If the model already gave text, stream it
                # out in small pieces for a responsive feel; otherwise fall
                # through to a fresh streamed completion below.
                if message.content:
                    yield message.content
                    return
                break

            for call in message.tool_calls:
                result = self.registry.dispatch(
                    call.function.name, call.function.arguments
                )
                self._history.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": result,
                    }
                )

        # Final answer: stream token deltas and accumulate for history.
        collected: list[str] = []
        try:
            stream = self._client.chat.completions.create(
                model=self.config.model,
                messages=self._history,
                stream=True,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta.content if chunk.choices else None
                if delta:
                    collected.append(delta)
                    yield delta
        except Exception as exc:  # noqa: BLE001 - fall back to a single reply
            if not collected:
                resp = self._client.chat.completions.create(
                    model=self.config.model, messages=self._history
                )
                text = resp.choices[0].message.content or ""
                collected.append(text)
                yield text
        self._history.append(
            {"role": "assistant", "content": "".join(collected)}
        )

    # -- Offline path -------------------------------------------------------

    def _offline_respond(self, user_input: str) -> str:
        """A minimal keyword router used when no API key is configured."""
        text = user_input.lower()

        if text.startswith("weather"):
            # e.g. "weather in Lisbon" / "weather Lisbon"
            loc = user_input[len("weather"):].strip().removeprefix("in ").strip()
            if loc:
                return self.registry.dispatch("get_weather", {"location": loc})
        if text.startswith(("search ", "look up ", "lookup ")):
            q = user_input.split(" ", 1)[1].strip() if " " in user_input else ""
            if text.startswith("look up "):
                q = user_input[len("look up "):].strip()
            if q:
                return self.registry.dispatch("web_search", {"query": q})
        # Power controls (these arm the confirmation gate; the next turn resolves it).
        if "shut down" in text or "shutdown" in text or "power off" in text:
            return self.registry.dispatch("shutdown_computer")
        if "restart" in text or "reboot" in text:
            return self.registry.dispatch("restart_computer")
        if any(w in text for w in ("suspend", "sleep", "hibernate")):
            return self.registry.dispatch("suspend_computer")

        # Spotify
        if text.startswith(("play ", "spotify")):
            if text in ("play", "spotify play") or text.startswith("spotify"):
                action = "play"
                if "pause" in text:
                    action = "pause"
                elif "next" in text or "skip" in text:
                    action = "next"
                elif "previous" in text or "back" in text:
                    action = "previous"
                return self.registry.dispatch("spotify_control", {"action": action})
            query = user_input[len("play "):].strip()
            return self.registry.dispatch(
                "spotify_control", {"action": "play", "query": query}
            )
        if text in ("pause", "pause music", "next track", "next", "skip"):
            action = "next" if text in ("next track", "next", "skip") else "pause"
            return self.registry.dispatch("spotify_control", {"action": action})

        # Timers & alarms
        if text.startswith("timer "):
            return self.registry.dispatch(
                "set_timer", {"duration": user_input[len("timer "):].strip()}
            )
        if text.startswith("alarm "):
            return self.registry.dispatch(
                "set_alarm", {"time": user_input[len("alarm "):].strip()}
            )
        if "list" in text and ("timer" in text or "alarm" in text or "reminder" in text):
            return self.registry.dispatch("list_reminders")

        # News
        if text.startswith("news") or text == "headlines":
            rest = user_input[len("news"):].strip().removeprefix("about ").strip()
            args = {"source": rest} if rest else {}
            return self.registry.dispatch("get_news", args)

        # Clipboard & notes
        if "clipboard" in text or text == "paste":
            return self.registry.dispatch("read_clipboard")
        # "remember ..." stores a durable fact (memory); "note ..." jots a note.
        if text.startswith("remember "):
            return self.registry.dispatch(
                "remember", {"fact": user_input[len("remember "):].strip()}
            )
        if text in ("what do you remember", "recall", "what do you know about me"):
            return self.registry.dispatch("recall")
        if text.startswith(("note ", "note that ")):
            for p in ("note that ", "note "):
                if text.startswith(p):
                    return self.registry.dispatch(
                        "add_note", {"text": user_input[len(p):].strip()}
                    )
        if text in ("read notes", "my notes", "notes"):
            return self.registry.dispatch("read_notes")

        # Calendar
        if any(w in text for w in ("calendar", "agenda", "schedule", "events today")):
            return self.registry.dispatch("get_calendar")

        # System controls
        if text.startswith("volume "):
            arg = user_input[len("volume "):].strip().rstrip("%")
            if arg in ("mute", "off"):
                return self.registry.dispatch("set_volume", {"mute": True})
            if arg in ("unmute", "on"):
                return self.registry.dispatch("set_volume", {"mute": False})
            return self.registry.dispatch("set_volume", {"level": arg})
        if text in ("mute", "unmute"):
            return self.registry.dispatch("set_volume", {"mute": text == "mute"})
        if text.startswith("brightness "):
            return self.registry.dispatch(
                "set_brightness", {"level": user_input[len("brightness "):].strip().rstrip("%")}
            )
        if "do not disturb" in text or text.startswith("dnd") or "focus" in text:
            on = not any(w in text for w in ("off", "disable", "stop"))
            return self.registry.dispatch("do_not_disturb", {"enable": on})

        # Screen description (needs online brain; skill explains if offline)
        if "describe" in text and "screen" in text:
            return self.registry.dispatch("describe_screen")

        # Dev shell
        if text.startswith(("run ", "git ", "pytest", "npm ")):
            cmd = user_input[len("run "):].strip() if text.startswith("run ") else user_input
            return self.registry.dispatch("run_command", {"command": cmd})

        if any(w in text for w in ("time", "date", "day")):
            return self.registry.dispatch("get_time")
        if any(w in text for w in ("system", "machine", "os", "computer")):
            return self.registry.dispatch("get_system_info")
        if text.startswith("open "):
            return self.registry.dispatch("open_app", {"name": user_input[5:].strip()})

        return (
            "I'm running without a connected brain at the moment, sir "
            "(no API key configured). Even so I can tell the time, report "
            "system info, open an app, fetch the weather or news, run a web "
            "lookup, control Spotify, set timers and alarms, read the clipboard, "
            "take notes, check your calendar, adjust volume/brightness/Do Not "
            "Disturb, run dev commands, or shut down / restart / suspend the "
            "machine. Set JARVIS_API_KEY for full conversation."
        )
