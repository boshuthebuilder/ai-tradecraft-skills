"""`--no-isolation-terms` for the tools that require a stated choice, in tests about something else.

`vision.py`, `structure.py` `measure` and `documents` and `wiki.py` `profile`, `bundles`, `brief` and `review-prompts`
refuse a command line with neither `--terms` nor `--no-isolation-terms`; a test that is not about the shield states
the second, as an operator with no other project to isolate would.
"""
SHIELDED = {"vision.py": None, "wiki.py": ("profile", "bundles", "brief", "review-prompts"),
            "structure.py": ("measure", "documents")}


def with_terms_flag(tool, args):
    """`args` with `--no-isolation-terms` added when the command needs a choice and `args` states none."""
    args = list(args)
    commands = SHIELDED.get(tool, ())
    if commands == () or (commands is not None and (args[:1] or [None])[0] not in commands):
        return args
    return args if "--terms" in args or "--no-isolation-terms" in args else args + ["--no-isolation-terms"]
