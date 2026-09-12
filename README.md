# eat

A tiny, slightly opinionated answer to **“what should I eat?”**

One Python script. Sixty meal ideas. No packages, accounts, or network calls.

## Just run it

You need Python 3.8 or newer. From this folder:

```sh
./eat
```

If executable permissions were lost while copying the file, use `python3 eat` or run `chmod +x eat` once.

It suggests one meal and exits. No setup, food knowledge, or input required.

```text
  No idea? I've got you.

  Bean quesadilla.

  Fold canned beans and cheese into a tortilla. Toast in a pan.
  10 min · cheap · quick · vegetarian · stovetop

```

That's it. Run `./eat` again if you want another idea.

To call it as `eat` from any directory, put the executable in a directory already on your `PATH`, or add this folder to your `PATH`. It works as a single file; the README and tests are optional.

## Try it in your browser

No Python handy? The same script is re-created as a browser terminal at <https://saltfish-len.github.io/eat-cli/>; type `eat` there. It runs the same menu, flags, remarks, streak rules, and overthinking, with saved data kept in your browser instead of `~/.config/eat/state.json`. The page is `web/index.html`; open it locally or let the GitHub Pages workflow publish it from `main`.

## Too much indecision

Repeated requests earn a different remark on every pick from 3 through 15. Request 15 is your last suggestion; request 16 gets a playful refusal and exits with status 1, without another meal or thinking animation.

A streak is a chain of picks no more than two minutes apart. A gap longer than two minutes after the last pick starts a fresh streak automatically. Refused requests do not extend the wait. For an immediate fresh start:

```sh
./eat reset
```

Reset clears the request streak, recent-pick history, and the once-per-streak thinking limit. Your personal meals and preferences stay saved. `list`, `add`, and `reset` remain available during a refusal and do not count as picks.

## Occasionally, it overthinks

About one in six terminal visits tries a fictional inner monologue: considering a meal, second-guessing it, wandering off on a food tangent, then finally settling on something ordinary. The full monologue runs at most once in a continuous request streak. Later attempts begin normally, then cut themselves off midway through the second thought and reveal the meal. This takes about a second, even with `--chaos`.

Thoughts stream in small word groups. Each completed thought stays visible for a reading pause based on its length, so longer thoughts get more time. The 14 short thoughts take about 30 seconds altogether, followed by the elapsed thinking time and the meal. **Press Enter at any point during thinking to reveal the meal immediately**, including during a reading pause. No input is required to finish normally. Ctrl-C exits the app cleanly.

Skipping with Enter also uses that streak's one full thinking opportunity, so later attempts use the brief self-interruption. Enter works during those brief attempts too. A gap longer than two minutes after the last pick or `./eat reset` allows a full monologue again. Enter-to-skip is available when keyboard input comes from a terminal; redirected input is left untouched.

It's scripted comedy styled like an AI thinking display, with no AI call. Both the final meal and any alternative mentioned come from your filtered menu. The monologue never changes the actual meal selection. The optional `./eat --chaos` shortcut requests thinking in a terminal and respects the once-per-streak limit.

## Optional shortcuts

You can do all the everyday deciding through `./eat`. These flags are available if you want them:

| Option | Meaning |
| --- | --- |
| `--quick` | About 15 minutes or less |
| `--cheap` | Meals using generally inexpensive ingredients |
| `--vegetarian` | No meat or fish; eggs and dairy may be included |
| `--chaos` | A sensible pick with deeply unserious reasoning |

Combine filters freely. Chaos always respects them. Times are estimates and assume the shortcuts mentioned in each suggestion. Cost tags are rough; adjust your personal meals to match your budget. Vegetarian labels assume vegetarian versions of cheeses, sauces, and other packaged ingredients.

Every built-in meal shows time, a diet category, and its main preparation method. For example, salmon is `25 min · fish · oven`; a chicken wrap is `10 min · quick · poultry · no cook`. Cheap and quick are added when applicable. A missing cheap tag does not imply a particular price. Personal meals keep the information you've provided and include a `personal meal` tag; missing dietary details are never guessed.

Run `./eat` again for another answer. It avoids the last five picks where possible. Small filtered menus rotate through their oldest picks. Reroll remarks appear in chaos mode too.

When output is redirected, `eat` prints one suggestion and exits immediately, without the monologue or animation delays. `--chaos` still adds a short joke in that mode. Keyboard input is checked only during terminal thinking.

See all matching options without changing your history:

```sh
./eat list
./eat list --quick --vegetarian
./eat --help
./eat add --help
```

## Optional personal meals

The built-in menu is ready from the first run. You can also add a familiar meal:

```sh
./eat add "Mom's curry"
./eat add "Emergency beans" --minutes 10 --cheap --vegetarian \
  --note "Heat a can of beans. Put them on toast."
```

Personal meals join the random pool. To appear under filters, give them the appropriate tags: `--minutes 15` or less for quick, `--cheap` for cheap, and `--vegetarian` for vegetarian. Unknown attributes are not assumed. Duplicate names are rejected, ignoring case.

If a future built-in meal shares a name with a personal meal you've already saved, your personal version takes precedence.

## Your local data

The first pick or addition creates one file at `~/.config/eat/state.json`. If `XDG_CONFIG_HOME` is set, the file lives at `$XDG_CONFIG_HOME/eat/state.json` instead. To use a different location:

```sh
EAT_HOME=./my-eat-data ./eat
```

The file stores personal meals, the last 30 picks, and default meal preferences. To set defaults, edit the existing `preferences` object:

```json
"preferences": {"vegetarian": true}
```

`quick` and `cheap` also accept `true` or `false`. Saved filters combine with command flags; set a preference to `false` to disable it. To remove a personal meal, delete its entry from the `meals` array. Keep the surrounding JSON valid. Invalid saved data produces an error and is left untouched.

The built-in catalog lives at the top of `eat` if you want to change its meals or jokes. No AI or API key required; the algorithm is just hungry randomness.

## Check it

```sh
python3 -m unittest discover -s tests -v
```

Tests use temporary data directories and leave your actual meal history alone.
