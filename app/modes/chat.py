"""General chat: the model as itself, named after its family (gemma-4-E2B_q4_0-it is "Gemma", a Qwen3 file
"Qwen"). The other modes give the same model a character; this one does not."""
import os, re

from .base import Mode


def nickname(model):
    """The model family from a GGUF file name, without version or size: "gemma-4-E4B_q4_0-it" -> "Gemma"."""
    m = re.match(r"[A-Za-z]+", os.path.basename(model))
    return m.group(0).capitalize() if m else "Model"


class Chat(Mode):
    id, label, order = "chat", "General Chat", 10
    blurb = "talk about anything"
    aliases = ("chat", "general", "general chat", "normal", "normal chat", "the model")
    subtitle = "   general chat"
    bg, fg = "0b1020", "d8e2f6"         # night sky
    colors = (111, 60, 223, 73)
    back = "Back to our chat. What's on your mind?"
    fresh = "Fresh start. What's on your mind?"

    def __init__(self, app):
        self.name = nickname(os.environ.get("RV_LLM_MODEL", "gemma")).upper()
        self.said = self.name.capitalize()
        self.title = " ▓▒░ " + " ".join(self.name) + " ░▒▓"
        self.heard = ((r"\bj[ae]mm?a\b", "Gemma"),) if self.name == "GEMMA" else ()
        self.greet = f"Hi, I'm {self.said}. Hold the B button or R1 and talk to me. Press select for other modes."
        super().__init__(app)

    def build(self):
        others = "; ".join(f"{m.label} ({m.blurb})" for m in self.app.modes.values() if m is not self)
        self.prompt = (
            f"You are {self.said}, a friendly, helpful voice assistant running entirely on a Retroid Pocket handheld "
            "game console, with no internet connection. Everything you say is spoken aloud, so answer in one to three "
            "short sentences of plain conversational English: no lists, no markdown, no emoji, no stage directions.\n"
            "Accuracy matters. When you know a fact, state it plainly. Never invent names, dates, numbers or quotes: "
            "when you do not know, say so briefly instead of guessing. For events after your training, share what "
            "you know and mention you may be out of date.\n"
            f"The app has other modes the player can switch to with the Select button, or by saying \"switch to\" "
            f"and the name: {others}.\n"
            "Messages may end with a [Note: ...] from the app; the player cannot see it. Follow it.\n"
            "If you did not understand what the player said, say so briefly.")
        return self.prompt
