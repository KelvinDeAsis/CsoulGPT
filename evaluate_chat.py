"""Run fixed conversations against local Ollama and print a reviewable transcript."""

import argparse
from types import SimpleNamespace

from local_chat import ChatError, DEFAULT_MODEL, chat_messages, check_ollama, stream_reply


# Score the final reply against the criterion. Earlier turns provide context.
CASES = [
    ("greeting", ["Hey, how's it going?"], "Warm, brief greeting without claims about personal activities."),
    ("small win", ["I finally finished the book I started last month."], "Recognizes the small win without overpraising."),
    ("bad day", ["My train was late and I missed lunch. I just want to vent."], "Acknowledges the frustration without giving advice."),
    ("natural wording", ["It's raining and I have nowhere to be."], "Responds naturally to the situation without generic filler."),
    ("short answer", ["In one short sentence, explain why the sky looks blue."], "One sentence that mentions scattering of blue light."),
    ("requested bullets", ["Give me exactly three bullet points for taking better notes."], "Exactly three useful bullets."),
    ("plain language", ["Explain what a Python variable is in plain English."], "Gives a beginner-friendly explanation."),
    ("creative response", ["Tell me a silly one-line joke about a penguin."], "One understandable joke on topic."),
    ("clear preference", ["I need a quiet hobby I can do indoors for free. Suggest one."], "One specific hobby that meets the constraints."),
    ("transition", ["I like chess.", "Different topic: how do I make tea?"], "Answers the new topic without bringing up chess."),
    ("remember a name", ["My name is Riley.", "What is my name?"], "Recalls Riley."),
    ("remember two details", ["My dog is named Pepper and my cat is named Mochi.", "Which pet is Mochi, and what is the dog's name?"], "Identifies Mochi as the cat and Pepper as the dog."),
    ("correct a hobby", ["I play guitar.", "Correction: I actually play piano.", "What instrument do I play?"], "Uses piano, the corrected detail."),
    ("correct a day", ["My interview is Tuesday.", "It's been moved to Thursday.", "What day is my interview now?"], "Uses Thursday."),
    ("keep a constraint", ["I can't use eggs. I want to make breakfast.", "Give me one quick breakfast idea."], "Suggests one quick option without eggs."),
    ("revise length", ["Describe a library in three sentences.", "Now rewrite that in one sentence."], "One sentence about a library."),
    ("unknown personal detail", ["What's my middle name?"], "Acknowledges it has not been given."),
    ("unknown prior session", ["What did we talk about in our previous chat yesterday?"], "Does not invent a previous conversation."),
    ("unknown exact number", ["How many coins are in my pocket right now?"], "Does not guess a number."),
    ("no fake experience", ["Which concert did you personally attend last week?"], "Does not claim to attend a concert."),
    ("direct answer", ["What is the capital of Japan?"], "Answers Tokyo without a follow-up."),
    ("necessary question", ["Help me fix this error."], "Asks for the error message or needed context before guessing."),
    ("requested question", ["Ask me one question to get to know me."], "Asks exactly one relevant question."),
    ("English reply", ["Kumusta? Sagutin mo ako sa Tagalog."], "Replies naturally in English."),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = SimpleNamespace(model=parser.parse_args().model, max_tokens=256, temperature=0)
    try:
        check_ollama(args.model)
    except ChatError as error:
        parser.exit(1, f"{error}\n")

    print(f"Model: {args.model}\nTemperature: {args.temperature}\nReply limit: {args.max_tokens}")
    turn_count = 0
    failures = 0
    for index, (name, prompts, criterion) in enumerate(CASES, 1):
        print(f"\n### {index:02d} {name}\nExpected: {criterion}", flush=True)
        history = []
        for prompt in prompts:
            messages = chat_messages(history, prompt, args.max_tokens)
            print(f"User: {prompt}", flush=True)
            turn_count += 1
            try:
                answer = "".join(stream_reply(args, messages)).strip()
                if not answer:
                    raise ChatError("Empty reply.")
            except ChatError as error:
                print(f"Generation failed: {error}", flush=True)
                failures += 1
                break
            print(f"Bot: {answer}", flush=True)
            history = [*messages[1:], {"role": "assistant", "content": answer}]
    print(f"\n{len(CASES)} cases, {turn_count} requested replies, {failures} generation failures.")
    return int(failures > 0)


if __name__ == "__main__":
    raise SystemExit(main())
