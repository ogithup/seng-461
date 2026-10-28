"""Example website specifications shared by the generator tests."""

BLOG = {
    "site_type": "blog",
    "title": "Travel Notes",
    "tagline": "Slow travel, good food and long walks.",
    "pages": [
        {"slug": "index", "title": "Home", "sections": [
            {"kind": "posts", "heading": "Latest posts", "body": "Newest first.", "items": [
                {"title": "Three days in Kapadokya", "meta": "Oct 2026", "body": "Balloons at dawn.",
                 "link": "posts.html#kapadokya"},
                {"title": "Ankara on foot", "meta": "Sep 2026", "body": "A walking route.",
                 "link": "posts.html#ankara-on-foot"},
            ]},
            {"heading": "Start here", "body": "Read the about page first.",
             "cta": {"label": "About me", "href": "about.html"}},
        ]},
        {"slug": "posts", "title": "Posts", "sections": [
            {"id": "kapadokya", "heading": "Three days in Kapadokya",
             "body": "Day one.\n\nDay two.\n\nDay three."},
            {"id": "ankara-on-foot", "heading": "Ankara on foot", "body": "Start at Kizilay."},
        ]},
        {"slug": "about", "title": "About", "sections": [
            {"heading": "Who writes here", "body": "A student who likes trains."},
        ]},
    ],
    "theme": {"primary": "#1e3a8a", "accent": "#f59e0b", "font": "serif"},
}

PORTFOLIO = {
    "site_type": "portfolio",
    "title": "Ada Lovelace",
    "tagline": "Analyst, writer, first programmer.",
    "pages": [
        {"slug": "index", "title": "Home", "sections": [
            {"kind": "hero", "heading": "I write programs for engines that do not exist yet.",
             "body": "Selected notes and projects.", "cta": {"label": "Projects", "href": "work.html"}},
            {"kind": "projects", "heading": "Featured", "items": [
                {"title": "Note G", "meta": "Algorithm", "body": "Bernoulli numbers.", "link": "work.html#note-g"},
                {"title": "Translation", "meta": "Writing", "body": "Menabrea's paper, annotated."},
            ]},
        ]},
        {"slug": "work", "title": "Work", "sections": [
            {"id": "note-g", "kind": "text", "heading": "Note G", "body": "The first published algorithm."},
        ]},
        {"slug": "contact", "title": "Contact", "sections": [
            {"kind": "cta", "heading": "Write to me", "body": "Letters welcome.",
             "cta": {"label": "Email", "href": "mailto:ada@example.com"}},
        ]},
    ],
    "theme": {"primary": "#111827", "accent": "#10b981"},
}

LANDING = {
    "site_type": "landing",
    "title": "Acme Notes",
    "tagline": "Notes that organise themselves.",
    "pages": [
        {"slug": "index", "title": "Home", "sections": [
            {"heading": "Write once, find it forever", "body": "Acme Notes tags everything for you.",
             "cta": {"label": "Try it free", "href": "#pricing"}},
            {"kind": "features", "heading": "Features", "items": [
                {"title": "Search", "body": "Instant results."},
                {"title": "Sync", "body": "Every device."},
                {"title": "Offline", "body": "Works on the train."},
            ]},
            {"kind": "cta", "id": "pricing", "heading": "Free for students",
             "body": "No card needed.", "cta": {"label": "Sign up", "href": "https://example.com/signup"}},
        ]},
        {"slug": "faq", "title": "FAQ", "sections": [
            {"heading": "Questions", "items": [
                {"title": "Is it free?", "body": "For students, yes."},
                {"title": "Can I export?", "body": "Markdown and HTML."},
            ]},
        ]},
    ],
    "theme": {"primary": "#fde68a", "accent": "#7c3aed", "font": "sans"},
    "footer": "Acme Inc. Made in Ankara.",
    "options": {"include_script": False},
}

ALL = {"blog": BLOG, "portfolio": PORTFOLIO, "landing": LANDING}
