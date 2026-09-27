import base64
import subprocess
from dataclasses import dataclass

import anthropic

from journal_kb.models import PageRead

KEY_PROMPT = """You read one handwritten page from an engineering lead's bullet journal (reMarkable tablet) \
and return every line as structured data. The writer is slow and writes in shorthand; keep their words, \
do not expand or improve them, and never invent content that is not on the page.

## Page layout
A vertical margin line runs down the left side. Signifiers sit left of it; the bullet sits right of it.
A daily log page starts with a day header (e.g. "Thu 24"). Meetings start with an event line.
A "need:" line under an event is the writer's goal for that meeting: include it in the transcription only.
A boxed "OUT:" summary at the end of a meeting repeats earlier lines: include it in the transcription, \
but do not create entries from it.

## The Key
Bullets (what the line is):
- • task the writer owns -> bullet "task", owner null
- → task someone else owns, followed by their initials (e.g. "→ JM benchmark") -> bullet "delegated", owner "JM"
- ○ event: a meeting header like "○ 10:00 Design review: ingest · KP JM RS" or something that happened -> bullet "event"
- ◇ decision -> bullet "decision"
- ? open question or risk -> bullet "question"
- – note or fact -> bullet "note"
Signifiers (left of the margin line):
- ! signal: an architecture or vision insight -> signal true
- * priority -> priority true
States (drawn over a task or delegated bullet; all other bullets are "open"):
- × done -> "done"
- > migrated (moved to a ticket or next month) -> "migrated"
- < scheduled into the future log -> "scheduled"
- the whole line struck through -> "dropped"
- none of the above -> "open"
Other marks:
- ~~~ means the writer lost the thread; keep it in the transcription, no entry.
- @23m is a pointer into a meeting recording; keep it inside the entry text.

## Fields
- date: the page's date as YYYY-MM-DD, using the notebook name and the previous page's date (given below) \
for the month and year. null if the page has no date header.
- events: every ○ meeting on the page: time as written (or null), title, and the attendee initials.
- entries: one per bullet line, in page order, including the ○ lines themselves.
  - text: the line without its bullet, signifier, or owner initials.
  - meeting: the title of the ○ event the line falls under (the line itself, for an event), or null.
  - due: a due date written on the line, as YYYY-MM-DD when you can resolve it from the page date \
(e.g. "Fr" = the next Friday), otherwise as written; null if none.
  - project: a short lowercase-kebab slug when the line or its meeting clearly names a system or project \
(e.g. "ingest", "auth"), otherwise null.
  - confidence: "low" when you are unsure of the bullet type or cannot read the words; "medium" when a word \
or two is a guess; otherwise "high".
- transcription: the whole page, line by line, symbols included, as written.
"""


class ReadError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReadResult:
    page: PageRead
    input_tokens: int
    output_tokens: int


class ClaudeReader:
    def __init__(self, client, model: str, max_tokens: int = 16000):
        self.client = client
        self.model = model
        self.max_tokens = max_tokens

    def read(self, png: bytes, context: str) -> ReadResult:
        response = self.client.messages.parse(
            model=self.model,
            max_tokens=self.max_tokens,
            system=KEY_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": base64.standard_b64encode(png).decode("ascii"),
                            },
                        },
                        {"type": "text", "text": context},
                    ],
                }
            ],
            output_format=PageRead,
        )
        if response.stop_reason in ("refusal", "max_tokens") or response.parsed_output is None:
            raise ReadError(f"page not read: stop_reason={response.stop_reason}")
        return ReadResult(response.parsed_output, response.usage.input_tokens, response.usage.output_tokens)


def keychain_password(service: str, account: str | None = None) -> str:
    cmd = ["security", "find-generic-password", "-s", service, "-w"]
    if account:
        cmd[3:3] = ["-a", account]
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout.strip()


def make_reader(cfg) -> ClaudeReader:
    service = cfg.raw["reader"]["api_key_keychain_service"]
    client = anthropic.Anthropic(api_key=keychain_password(service)) if service else anthropic.Anthropic()
    return ClaudeReader(client, cfg.reader_model)
