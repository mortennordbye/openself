# Working with an AI assistant

OpenSelf is built for an assistant to work next to you, without taking over. The web app never
calls an AI itself. It stores your requests, and an assistant session on your machine (Claude Code,
or another) picks them up, interviews you, and writes your answers into the profile.

## The rules

Every home has an `AGENTS.md` that assistants follow. The short version:

- **Only you add facts.** The assistant writes your own words, never guesses, and turns what it
  does not know into a `⚑ question:` for you.
- **Every change is a commit** marked with the actor: `<id>: <what> [claude]`.
- **It may push, never decrypt.** Pushing needs only the public keys. Decrypting, the secret key,
  approving recipients and changing repository settings are yours.
- **Nothing from the profile goes into the home repository**, a commit message, an issue or a pull
  request.

## Asking from the web app

On an entry, **Ask about this**; on an open question, **Ask me about this**; on a new entry,
**Save and ask me**. Each stores a request in the profile's `.git` folder (never committed). To
have an assistant answer them, run in the home:

```sh
make ai
```

It starts Claude Code, already told to run `./self assistant watch` as a background monitor. The AI
chip in the web app turns green while it runs. For each request the assistant reads the entry and
its flags, asks you short questions in its own window, writes your answers in, commits, runs
`make check`, and marks the request done with a note the web app shows.

With another assistant, start the same watcher yourself:

```sh
./self assistant watch      # prints each request as it arrives
./self assistant list       # the requests and their status
./self assistant done 3 --note "added team size and your own contribution"
```

## Starting from old CVs

The prompts from `make check` are the interview list: missing roles, team sizes, your own
contribution, open conflicts. An assistant can work through them with you one topic at a time.
OpenVita can also start you off: put old CVs and a LinkedIn PDF in its intake folder and run
`/onboard` in Claude Code there (see the
[OpenVita README](https://github.com/mortennordbye/openvita#start)).

## Citing the profile

Anything an assistant writes from the profile for others (a CV, an answer, a form) should point
each claim back to the entry it rests on: `<id>` or `<id>#<section>`. The ids never change, so a
citation stays valid, and the history shows who wrote each line.
