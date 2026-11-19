# Agent module

The rule-based interpreter turns a request into a validated generator spec for a blog, portfolio, or landing page. It uses the Sprint 3 planner for site type and title; absent details use its default title and Rana's starter content and theme. The default blog retains the Sprint 3 file set; request `page: Archive` to add an archive page. Known unsupported requests such as online shops raise `UnsupportedRequest`; the API translates that exception to a user-facing 422. No model credentials are required.

Explicit fields use semicolon-separated labels, for example:

```
Create a landing page for Acme; page: Pricing; section: Benefits; primary: #123456; accent: #abcdef; font: serif
```

`page`/`pages` add named pages (comma-separated); `section` adds a heading to the home page. New pages and sections receive placeholder body text. `primary` and `accent` require six-digit hex colors; `font` is `sans`, `serif`, or `mono`. Invalid values are rejected by `normalize_spec`. This interpreter recognizes these explicit labels and simple type/title cues; it does not interpret arbitrary prose as a feature specification.

`Orchestrator(generator=None, interpreter=None)` accepts a callable interpreter returning a spec. It validates that output, generates a plan with one write task per file, and reconstructs each spec from the task prompt without in-memory state. It accepts legacy prompts and the previous encoded-spec prompt format. The executor performs and verifies writes; the agent does not access the filesystem, database, shell, or network.

The API currently truncates task prompts to 500 characters. Custom specs are stored as compressed changes from the starter; plans that still exceed the limit are rejected before tasks are created. Supporting arbitrary valid large specs requires an agreed task payload or persistence contract with Oğuz; this module does not change storage or shared interfaces.
