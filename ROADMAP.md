# Roadmap

This is where Minion is going. Nothing here has a date. If you'd like to work on something, comment on its issue or
start a [discussion](https://github.com/apophisss/minion/discussions) first, so that two people don't build the same
thing. A 👍 on an issue helps decide what comes first.

## Now: help wanted

These are small tasks with clear steps, labelled
[good first issue](https://github.com/apophisss/minion/labels/good%20first%20issue):

- The README in Spanish ([#4](https://github.com/apophisss/minion/issues/4)), Portuguese
  ([#5](https://github.com/apophisss/minion/issues/5)) and German ([#6](https://github.com/apophisss/minion/issues/6)).
- Reports from real macOS ([#7](https://github.com/apophisss/minion/issues/7)) and Windows
  ([#8](https://github.com/apophisss/minion/issues/8)) machines.
- More apps an agent can open by name ([#9](https://github.com/apophisss/minion/issues/9)), more agent apps for
  `minion connect` ([#10](https://github.com/apophisss/minion/issues/10)), and more benchmark tasks
  ([#11](https://github.com/apophisss/minion/issues/11)).
- A recipes page ([#12](https://github.com/apophisss/minion/issues/12)) and a `design` profile
  ([#13](https://github.com/apophisss/minion/issues/13)).

## Next

- **Network allowlists** ([#14](https://github.com/apophisss/minion/issues/14)). Today a desktop has the whole network
  or none (`--offline`). An allowlist would let it reach only the sites a task needs.
- **Secrets the model never sees** ([#15](https://github.com/apophisss/minion/issues/15)). The agent refers to a
  password by name and Minion types it, so it never enters the model's context, recordings or logs.
- **Task success, measured** ([#16](https://github.com/apophisss/minion/issues/16)). An OSWorld-style suite that
  reports how often agents finish real tasks, next to the [token benchmark](docs/benchmarks.md).
- **Video recordings** ([#17](https://github.com/apophisss/minion/issues/17)). `minion replay` as MP4, next to the
  HTML timeline, GIF and replayable script it exports today.

## Later

- **Stronger isolation.** Optional gVisor or microVM (Kata, Firecracker) runtimes for untrusted agents and files.
- **A hosted playground.** Try Minion from a browser without installing anything.
- **More desktops.** Profiles for design, video, GIS and accounting work, and GPU acceleration for 3D apps.

## Not planned

- **Telemetry.** Minion never reports anything anywhere.
- **Host dependencies.** The host side stays pure Python standard library, so it installs anywhere in seconds.
